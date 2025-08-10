"""Support for Frigate cameras."""

from __future__ import annotations

import datetime
import logging
from typing import Any

import async_timeout
from jinja2 import Template
import voluptuous as vol
from yarl import URL

from custom_components.frigate.api import FrigateApiClient
from homeassistant.components.camera import (
    Camera,
    CameraEntityFeature,
    WebRTCAnswer,
    WebRTCSendMessage,
)
from homeassistant.components.mqtt import async_publish
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    decode_if_necessary,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
    verify_frigate_version,
)
from .const import (
    ATTR_CLIENT,
    ATTR_CONFIG,
    ATTR_COORDINATOR,
    ATTR_DURATION,
    ATTR_END_TIME,
    ATTR_EVENT_ID,
    ATTR_FAVORITE,
    ATTR_INCLUDE_RECORDING,
    ATTR_LABEL,
    ATTR_PLAYBACK_FACTOR,
    ATTR_PTZ_ACTION,
    ATTR_PTZ_ARGUMENT,
    ATTR_START_TIME,
    ATTR_SUB_LABEL,
    CONF_ENABLE_WEBRTC,
    CONF_RTSP_URL_TEMPLATE,
    DEVICE_CLASS_CAMERA,
    DOMAIN,
    NAME,
    SERVICE_CREATE_EVENT,
    SERVICE_END_EVENT,
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

    frigate_webrtc = entry.options.get(CONF_ENABLE_WEBRTC, False)
    camera_type = FrigateCameraWebRTC if frigate_webrtc else FrigateCamera
    birdseye_type = BirdseyeCameraWebRTC if frigate_webrtc else BirdseyeCamera

    async_add_entities(
        [
            camera_type(
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
            [birdseye_type(entry, frigate_client)]
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
    platform.async_register_entity_service(
        SERVICE_CREATE_EVENT,
        {
            vol.Required(ATTR_LABEL): str,
            vol.Optional(ATTR_SUB_LABEL, default=""): str,
            vol.Optional(ATTR_DURATION, default=30): int,
            vol.Optional(ATTR_INCLUDE_RECORDING, default=True): bool,
        },
        SERVICE_CREATE_EVENT,
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        SERVICE_END_EVENT,
        {
            vol.Required(ATTR_EVENT_ID): str,
        },
        SERVICE_END_EVENT,
        supports_response=SupportsResponse.OPTIONAL,
    )


class FrigateCamera(
    FrigateMQTTEntity, CoordinatorEntity[FrigateDataUpdateCoordinator], Camera
):
    """A Frigate camera."""

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
                "enabled_topic": {
                    "msg_callback": self._enabled_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/enabled/state"
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
            self._cam_name
            in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
        )
        self._attr_is_recording = self._camera_config.get("record", {}).get("enabled")
        self._attr_motion_detection_enabled = self._camera_config.get("motion", {}).get(
            "enabled"
        )
        self._turn_on_off_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/enabled/set"
        )
        self._ptz_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/ptz"
        )
        self._set_motion_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/motion/set"
        )

        if self._attr_is_streaming:
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

    @callback
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._attr_is_recording = decode_if_necessary(msg.payload) == "ON"
        self.async_write_ha_state()

    @callback
    def _motion_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT extra message."""
        self._attr_motion_detection_enabled = decode_if_necessary(msg.payload) == "ON"
        self.async_write_ha_state()

    @callback
    def _enabled_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT extra message."""
        self._attr_is_on = decode_if_necessary(msg.payload) == "ON"

        if self._attr_is_on:
            self._attr_is_streaming = (
                self._cam_name
                in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
            )
            self._attr_is_recording = self._camera_config.get("record", {}).get(
                "enabled"
            )
        else:
            self._attr_is_streaming = False
            self._attr_is_recording = False

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Signal when frigate loses connection to camera."""
        if not self._attr_is_on:
            # if the camera is off it may appear unavailable
            # but it should be available for service calls
            return True

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
    def device_info(self) -> DeviceInfo:
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
        websession = async_get_clientsession(
            self.hass, verify_ssl=self._client.validate_ssl
        )

        image_url = str(
            URL(self._url)
            / f"api/{self._cam_name}/latest.jpg"
            % ({"h": height} if height is not None and height > 0 else {})
        )

        headers = await self._client.get_auth_headers()
        async with async_timeout.timeout(10):
            response = await websession.get(image_url, headers=headers)
            return await response.read()

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        return self._stream_source

    async def async_turn_on(self) -> None:
        """Turn on the camera."""
        if verify_frigate_version(self._frigate_config, "0.16"):
            await async_publish(
                self.hass,
                self._turn_on_off_topic,
                "ON",
                0,
                False,
            )

    async def async_turn_off(self) -> None:
        """Turn off the camera."""
        if verify_frigate_version(self._frigate_config, "0.16"):
            await async_publish(
                self.hass,
                self._turn_on_off_topic,
                "OFF",
                0,
                False,
            )

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

    async def create_event(
        self, label: str, sub_label: str, duration: int, include_recording: bool
    ) -> dict[str, Any]:
        """Create an event."""
        if label == "":
            raise ServiceValidationError("Label cannot be empty")

        return await self._client.async_create_event(
            self._cam_name,
            label,
            sub_label,
            duration if duration > 0 else None,
            include_recording,
        )

    async def end_event(self, event_id: str) -> dict[str, Any]:
        """End an event."""
        if event_id == "":
            raise ServiceValidationError("Event ID cannot be empty")

        return await self._client.async_end_event(event_id)


class BirdseyeCamera(FrigateEntity, Camera):
    """A Frigate birdseye camera."""

    # sets the entity name to same as device name ex: camera.front_doorbell
    _attr_name = None

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_client: FrigateApiClient,
    ) -> None:
        """Initialize the birdseye camera."""
        self._client = frigate_client
        self._cam_name = "birdseye"
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
                {"name": self._cam_name}
            )
        else:
            self._stream_source = f"rtsp://{URL(self._url).host}:8554/{self._cam_name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera",
            "birdseye",
        )

    @property
    def device_info(self) -> DeviceInfo:
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
        websession = async_get_clientsession(
            self.hass, verify_ssl=self._client.validate_ssl
        )

        image_url = str(
            URL(self._url)
            / f"api/{self._cam_name}/latest.jpg"
            % ({"h": height} if height is not None and height > 0 else {})
        )

        headers = await self._client.get_auth_headers()
        async with async_timeout.timeout(10):
            response = await websession.get(image_url, headers=headers)
            return await response.read()

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        return self._stream_source


class FrigateCameraWebRTC(FrigateCamera):
    """A Frigate camera with WebRTC support."""

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        """Handle the WebRTC offer and return an answer."""
        websession = async_get_clientsession(
            self.hass, verify_ssl=self._client.validate_ssl
        )
        url = f"{self._url}/api/go2rtc/webrtc?src={self._cam_name}"
        payload = {"type": "offer", "sdp": offer_sdp}
        headers = await self._client.get_auth_headers()
        async with websession.post(url, json=payload, headers=headers) as resp:
            answer = await resp.json()
            send_message(WebRTCAnswer(answer["sdp"]))

    async def async_on_webrtc_candidate(self, session_id: str, candidate: Any) -> None:
        """Ignore WebRTC candidates for Frigate cameras."""
        return


class BirdseyeCameraWebRTC(BirdseyeCamera):
    """A Frigate birdseye camera with WebRTC support."""

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        """Handle the WebRTC offer and return an answer."""
        websession = async_get_clientsession(
            self.hass, verify_ssl=self._client.validate_ssl
        )
        url = f"{self._url}/api/go2rtc/webrtc?src={self._cam_name}"
        payload = {"type": "offer", "sdp": offer_sdp}
        headers = await self._client.get_auth_headers()
        async with websession.post(url, json=payload, headers=headers) as resp:
            answer = await resp.json()
            send_message(WebRTCAnswer(answer["sdp"]))

    async def async_on_webrtc_candidate(self, session_id: str, candidate: Any) -> None:
        """Ignore WebRTC candidates for Frigate cameras."""
        return
