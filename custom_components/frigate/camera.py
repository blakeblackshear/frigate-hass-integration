"""Support for Frigate cameras."""
from __future__ import annotations

import logging
from typing import Any

import async_timeout
from yarl import URL

from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.components.mqtt.models import Message
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateEntity,
    FrigateMQTTEntity,
    get_cameras_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
)
from .const import DOMAIN, NAME, STATE_DETECTED, STATE_IDLE, VERSION

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Camera entry setup."""

    config = hass.data[DOMAIN]["config"]

    async_add_entities(
        [
            FrigateCamera(entry, name, camera)
            for name, camera in config["cameras"].items()
        ]
        + [
            FrigateMqttSnapshots(entry, config, cam_name, obj_name)
            for cam_name, obj_name in get_cameras_and_objects(config)
        ]
    )


class FrigateCamera(FrigateEntity, Camera):
    """Representation a Frigate camera."""

    def __init__(
        self, config_entry: ConfigEntry, name: str, config: dict[str, Any]
    ) -> None:
        """Initialize a Frigate camera."""
        FrigateEntity.__init__(self, config_entry)
        Camera.__init__(self)
        self._name = name
        self._config = config
        self._host = config_entry.data["host"]
        self._latest_url = str(
            URL(self._host) / f"api/{self._name}/latest.jpg" % {"h": 277}
        )
        self._stream_source = f"rtmp://{URL(self._host).host}/live/{self._name}"
        self._stream_enabled = self._config["rtmp"]["enabled"]

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._name}_camera"

    @property
    def name(self) -> str:
        """Return the name of the camera."""
        return get_friendly_name(self._name)

    @property
    def device_info(self) -> dict[str, any]:
        """Return the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._name),
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def supported_features(self) -> int:
        """Return supported features of this camera."""
        if not self._stream_enabled:
            return 0
        return SUPPORT_STREAM

    async def async_camera_image(self) -> bytes:
        """Return bytes of camera image."""
        websession = async_get_clientsession(self.hass)

        with async_timeout.timeout(10):
            response = await websession.get(self._latest_url)
            return await response.read()

    async def stream_source(self) -> str:
        """Return the source of the stream."""
        if not self._stream_enabled:
            return None
        return self._stream_source


class FrigateMqttSnapshots(FrigateMQTTEntity, Camera):
    """Frigate best camera class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateMqttSnapshots camera."""
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._last_image = None

        FrigateMQTTEntity.__init__(
            self,
            config_entry,
            frigate_config,
            {
                "topic": (
                    f"{frigate_config['mqtt']['topic_prefix']}"
                    f"/{self._cam_name}/{self._obj_name}/snapshot"
                ),
                "encoding": None,
            },
        )
        Camera.__init__(self)

    @callback
    def _state_message_received(self, msg: Message) -> None:
        """Handle a new received MQTT state message."""
        self._last_image = msg.payload
        super()._state_message_received(msg)

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}_snapshot"

    @property
    def device_info(self) -> DeviceInfo:
        """Get the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._obj_name}".title()

    async def async_camera_image(self) -> bytes:
        """Return image response."""
        return self._last_image

    @property
    def state(self) -> str:
        """Return the camera state."""
        if self._last_image is None:
            return STATE_IDLE
        return STATE_DETECTED
