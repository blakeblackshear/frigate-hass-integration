"""Support for Frigate cameras."""
from __future__ import annotations

import datetime
import logging
from typing import Any, cast

import aiohttp
import async_timeout
from jinja2 import Template
import voluptuous as vol
from yarl import URL

from custom_components.frigate.api import FrigateApiClient
from homeassistant.components.camera import Camera, CameraEntityFeature, StreamType
from homeassistant.components.mqtt import async_publish
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CLIENT,
    ATTR_CONFIG,
    ATTR_COORDINATOR,
    ATTR_END_TIME,
    ATTR_EVENT_ID,
    ATTR_FAVORITE,
    ATTR_PLAYBACK_FACTOR,
    ATTR_PTZ_ACTION,
    ATTR_PTZ_ARGUMENT,
    ATTR_START_TIME,
    CONF_ENABLE_WEBRTC,
    CONF_RTMP_URL_TEMPLATE,
    CONF_RTSP_URL_TEMPLATE,
    DEVICE_CLASS_CAMERA,
    DOMAIN,
    NAME,
    SERVICE_EXPORT_RECORDING,
    SERVICE_FAVORITE_EVENT,
    SERVICE_PTZ,
)
from .views import get_frigate_instance_id_for_config_entry

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Camera entry setup."""

    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    frigate_client = hass.data[DOMAIN][entry.entry_id][ATTR_CLIENT]
    client_id = get_frigate_instance_id_for_config_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id][ATTR_COORDINATOR]

    async_add_entities(
        [
            FrigateCamera(
                entry,
                cam_name,
                frigate_client,
                client_id,
                coordinator,
                frigate_config,
                camera_config,
            )
            for cam_name, camera_config in frigate_config["cameras"].items()
        ]
        + (
            [BirdseyeCamera(entry, frigate_client)]
            if frigate_config.get("birdseye", {}).get("restream", False)
            else []
        )
    )

    # setup services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_EXPORT_RECORDING,
        {
            vol.Required(ATTR_PLAYBACK_FACTOR, default="realtime"): str,
            vol.Required(ATTR_START_TIME): str,
            vol.Required(ATTR_END_TIME): str,
        },
        SERVICE_EXPORT_RECORDING,
    )
    platform.async_register_entity_service(
        SERVICE_FAVORITE_EVENT,
        {
            vol.Required(ATTR_EVENT_ID): str,
            vol.Optional(ATTR_FAVORITE, default=True): bool,
        },
        SERVICE_FAVORITE_EVENT,
    )
    platform.async_register_entity_service(
        SERVICE_PTZ,
        {
            vol.Required(ATTR_PTZ_ACTION): str,
            vol.Optional(ATTR_PTZ_ARGUMENT, default=""): str,
        },
        SERVICE_PTZ,
    )


class FrigateCamera(FrigateMQTTEntity, CoordinatorEntity, Camera):  # type: ignore[misc]
    """Representation of a Frigate camera."""

    # sets the entity name to same as device name ex: camera.front_doorbell
    _attr_name = None

    def __init__(
        self,
        config_entry: ConfigEntry,
        cam_name: str,
        frigate_client: FrigateApiClient,
        frigate_client_id: Any | None,
        coordinator: FrigateDataUpdateCoordinator,
        frigate_config: dict[str, Any],
        camera_config: dict[str, Any],
    ) -> None:
        """Initialize a Frigate camera."""
        self._client = frigate_client
        self._client_id = frigate_client_id
        self._frigate_config = frigate_config
        self._camera_config = camera_config
        self._cam_name = cam_name
        super().__init__(
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/recordings/state"
                    ),
                    "encoding": None,
                },
                "motion_topic": {
                    "msg_callback": self._motion_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/motion/state"
                    ),
                    "encoding": None,
                },
            },
        )
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._url = config_entry.data[CONF_URL]
        self._attr_is_on = True
        # The device_class is used to filter out regular camera entities
        # from motion camera entities on selectors
        self._attr_device_class = DEVICE_CLASS_CAMERA
        self._stream_source = None
        self._attr_is_streaming = (
            self._camera_config.get("rtmp", {}).get("enabled")
            or self._cam_name
            in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
        )
        self._attr_is_recording = self._camera_config.get("record", {}).get("enabled")
        self._attr_motion_detection_enabled = self._camera_config.get("motion", {}).get(
            "enabled"
        )
        self._ptz_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/ptz"
        )
        self._set_motion_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/motion/set"
        )

        if (
            self._cam_name
            in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
        ):
            if config_entry.options.get(CONF_ENABLE_WEBRTC, False):
                self._restream_type = "webrtc"
                self._attr_frontend_stream_type = StreamType.WEB_RTC
            else:
                self._restream_type = "rtsp"
                self._attr_frontend_stream_type = StreamType.HLS

            streaming_template = config_entry.options.get(
                CONF_RTSP_URL_TEMPLATE, ""
            ).strip()

            if streaming_template:
                # Can't use homeassistant.helpers.template as it requires hass which
                # is not available in the constructor, so use direct jinja2
                # template instead. This means templates cannot access HomeAssistant
                # state, but rather only the camera config.
                self._stream_source = Template(streaming_template).render(
                    **self._camera_config
                )
            else:
                self._stream_source = (
                    f"rtsp://{URL(self._url).host}:8554/{self._cam_name}"
                )
        elif self._camera_config.get("rtmp", {}).get("enabled"):
            self._restream_type = "rtmp"
            streaming_template = config_entry.options.get(
                CONF_RTMP_URL_TEMPLATE, ""
            ).strip()

            if streaming_template:
                # Can't use homeassistant.helpers.template as it requires hass which
                # is not available in the constructor, so use direct jinja2
                # template instead. This means templates cannot access HomeAssistant
                # state, but rather only the camera config.
                self._stream_source = Template(streaming_template).render(
                    **self._camera_config
                )
            else:
                self._stream_source = (
                    f"rtmp://{URL(self._url).host}/live/{self._cam_name}"
                )
        else:
            self._restream_type = "none"

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._attr_is_recording = msg.payload.decode("utf-8") == "ON"
        self.async_write_ha_state()

    @callback  # type: ignore[misc]
    def _motion_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT extra message."""
        self._attr_motion_detection_enabled = msg.payload.decode("utf-8") == "ON"
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Signal when frigate loses connection to camera."""
        if self.coordinator.data:
            if (
                self.coordinator.data.get("cameras", {})
                .get(self._cam_name, {})
                .get("camera_fps", 0)
                == 0
            ):
                return False
        return super().available

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera",
            self._cam_name,
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": self._get_model(),
            "configuration_url": f"{self._url}/cameras/{self._cam_name}",
            "manufacturer": NAME,
        }

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return entity specific state attributes."""
        return {
            "client_id": str(self._client_id),
            "camera_name": self._cam_name,
            "restream_type": self._restream_type,
        }

    @property
    def supported_features(self) -> CameraEntityFeature:
        """Return supported features of this camera."""
        if not self._attr_is_streaming:
            return CameraEntityFeature(0)

        return CameraEntityFeature.STREAM

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        websession = cast(aiohttp.ClientSession, async_get_clientsession(self.hass))

        image_url = str(
            URL(self._url)
            / f"api/{self._cam_name}/latest.jpg"
            % ({"h": height} if height is not None and height > 0 else {})
        )

        async with async_timeout.timeout(10):
            response = await websession.get(image_url)
            return await response.read()

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        if not self._attr_is_streaming:
            return None
        return self._stream_source

    async def async_handle_web_rtc_offer(self, offer_sdp: str) -> str | None:
        """Handle the WebRTC offer and return an answer."""
        websession = cast(aiohttp.ClientSession, async_get_clientsession(self.hass))
        url = f"{self._url}/api/go2rtc/webrtc?src={self._cam_name}"
        payload = {"type": "offer", "sdp": offer_sdp}
        async with websession.post(url, json=payload) as resp:
            answer = await resp.json()
            return cast(str, answer["sdp"])

    async def async_enable_motion_detection(self) -> None:
        """Enable motion detection for this camera."""
        await async_publish(
            self.hass,
            self._set_motion_topic,
            "ON",
            0,
            False,
        )

    async def async_disable_motion_detection(self) -> None:
        """Disable motion detection for this camera."""
        await async_publish(
            self.hass,
            self._set_motion_topic,
            "OFF",
            0,
            False,
        )

    async def export_recording(
        self, playback_factor: str, start_time: str, end_time: str
    ) -> None:
        """Export recording."""
        await self._client.async_export_recording(
            self._cam_name,
            playback_factor,
            datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp(),
            datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp(),
        )

    async def favorite_event(self, event_id: str, favorite: bool) -> None:
        """Favorite an event."""
        await self._client.async_retain(event_id, favorite)

    async def ptz(self, action: str, argument: str) -> None:
        """Run PTZ command."""
        await async_publish(
            self.hass,
            self._ptz_topic,
            f"{action}{f'_{argument}' if argument else ''}",
            0,
            False,
        )


class BirdseyeCamera(FrigateEntity, Camera):  # type: ignore[misc]
    """Representation of the Frigate birdseye camera."""

    # sets the entity name to same as device name ex: camera.front_doorbell
    _attr_name = None

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_client: FrigateApiClient,
    ) -> None:
        """Initialize the birdseye camera."""
        self._client = frigate_client
        FrigateEntity.__init__(self, config_entry)
        Camera.__init__(self)
        self._url = config_entry.data[CONF_URL]
        self._attr_is_on = True
        # The device_class is used to filter out regular camera entities
        # from motion camera entities on selectors
        self._attr_device_class = DEVICE_CLASS_CAMERA
        self._attr_is_streaming = True
        self._attr_is_recording = False

        streaming_template = config_entry.options.get(
            CONF_RTSP_URL_TEMPLATE, ""
        ).strip()

        if streaming_template:
            # Can't use homeassistant.helpers.template as it requires hass which
            # is not available in the constructor, so use direct jinja2
            # template instead. This means templates cannot access HomeAssistant
            # state, but rather only the camera config.
            self._stream_source = Template(streaming_template).render(
                {"name": "birdseye"}
            )
        else:
            self._stream_source = f"rtsp://{URL(self._url).host}:8554/birdseye"

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera",
            "birdseye",
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, "birdseye")
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": "Birdseye",
            "model": self._get_model(),
            "configuration_url": f"{self._url}/cameras/birdseye",
            "manufacturer": NAME,
        }

    @property
    def supported_features(self) -> CameraEntityFeature:
        """Return supported features of this camera."""
        return CameraEntityFeature.STREAM

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        websession = cast(aiohttp.ClientSession, async_get_clientsession(self.hass))

        image_url = str(
            URL(self._url)
            / "api/birdseye/latest.jpg"
            % ({"h": height} if height is not None and height > 0 else {})
        )

        async with async_timeout.timeout(10):
            response = await websession.get(image_url)
            return await response.read()

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        return self._stream_source
