"""Support for Frigate cameras."""
from __future__ import annotations

import logging
from typing import Any, cast

import aiohttp
import async_timeout
from jinja2 import Template
import voluptuous as vol
from yarl import URL

from custom_components.frigate.api import FrigateApiClient
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.mqtt import async_publish
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CLIENT,
    ATTR_CONFIG,
    ATTR_EVENT_ID,
    ATTR_FAVORITE,
    CONF_RTMP_URL_TEMPLATE,
    CONF_RTSP_URL_TEMPLATE,
    DEVICE_CLASS_CAMERA,
    DOMAIN,
    NAME,
    SERVICE_FAVORITE_EVENT,
    STATE_DETECTED,
    STATE_IDLE,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Camera entry setup."""

    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    frigate_client = hass.data[DOMAIN][entry.entry_id][ATTR_CLIENT]

    async_add_entities(
        [
            FrigateCamera(
                entry, cam_name, frigate_client, frigate_config, camera_config
            )
            for cam_name, camera_config in frigate_config["cameras"].items()
        ]
        + [
            FrigateMqttSnapshots(entry, frigate_config, cam_name, obj_name)
            for cam_name, obj_name in get_cameras_and_objects(frigate_config, False)
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
        SERVICE_FAVORITE_EVENT,
        {
            vol.Required(ATTR_EVENT_ID): str,
            vol.Optional(ATTR_FAVORITE, default=True): bool,
        },
        SERVICE_FAVORITE_EVENT,
    )


class FrigateCamera(FrigateMQTTEntity, Camera):  # type: ignore[misc]
    """Representation of a Frigate camera."""

    # sets the entity name to same as device name ex: camera.front_doorbell
    _attr_name = None

    def __init__(
        self,
        config_entry: ConfigEntry,
        cam_name: str,
        frigate_client: FrigateApiClient,
        frigate_config: dict[str, Any],
        camera_config: dict[str, Any],
    ) -> None:
        """Initialize a Frigate camera."""
        self._client = frigate_client
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
        Camera.__init__(self)
        self._url = config_entry.data[CONF_URL]
        self._attr_is_on = True
        # The device_class is used to filter out regular camera entities
        # from motion camera entities on selectors
        self._attr_device_class = DEVICE_CLASS_CAMERA
        self._attr_is_streaming = (
            self._camera_config.get("rtmp", {}).get("enabled")
            or self._cam_name
            in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
        )
        self._attr_is_recording = self._camera_config.get("record", {}).get("enabled")
        self._attr_motion_detection_enabled = self._camera_config.get("motion", {}).get(
            "enabled"
        )
        self._set_motion_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}" f"/{self._cam_name}/motion/set"
        )

        if (
            self._cam_name
            in self._frigate_config.get("go2rtc", {}).get("streams", {}).keys()
        ):
            self._restream_type = "rtsp"
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
            "restream_type": self._restream_type,
        }

    @property
    def supported_features(self) -> int:
        """Return supported features of this camera."""
        if not self._attr_is_streaming:
            return 0

        return cast(int, CameraEntityFeature.STREAM)

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

    async def favorite_event(self, event_id: str, favorite: bool) -> None:
        """Favorite an event."""
        await self._client.async_retain(event_id, favorite)


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
    def supported_features(self) -> int:
        """Return supported features of this camera."""
        return cast(int, CameraEntityFeature.STREAM)

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


class FrigateMqttSnapshots(FrigateMQTTEntity, Camera):  # type: ignore[misc]
    """Frigate best camera class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateMqttSnapshots camera."""
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._last_image: bytes | None = None

        FrigateMQTTEntity.__init__(
            self,
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/{self._obj_name}/snapshot"
                    ),
                    "encoding": None,
                },
            },
        )
        Camera.__init__(self)

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._last_image = msg.payload
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera_snapshots",
            f"{self._cam_name}_{self._obj_name}",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": self._get_model(),
            "configuration_url": f"{self._config_entry.data.get(CONF_URL)}/cameras/{self._cam_name}",
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._obj_name.title()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return image response."""
        return self._last_image

    @property
    def state(self) -> str:
        """Return the camera state."""
        if self._last_image is None:
            return STATE_IDLE
        return STATE_DETECTED
