"""Support for Frigate cameras."""
from __future__ import annotations

import logging
from typing import Any
import urllib.parse

import async_timeout

from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_cameras_and_objects, get_friendly_name, get_frigate_device_identifier
from .const import DOMAIN, NAME, STATE_DETECTED, STATE_IDLE, VERSION

_LOGGER: logging.Logger = logging.getLogger(__package__)


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


class FrigateCamera(Camera):
    """Representation a Frigate camera."""

    def __init__(
        self, config_entry: ConfigEntry, name: str, config: dict[str, Any]
    ) -> None:
        """Initialize a Frigate camera."""
        super().__init__()

        self._config_entry = config_entry
        self._name = name
        self._config = config
        self._host = config_entry.data["host"]
        self._latest_url = urllib.parse.urljoin(
            self._host, f"/api/{self._name}/latest.jpg?h=277"
        )
        parsed_host = urllib.parse.urlparse(self._host).hostname
        self._stream_source = f"rtmp://{parsed_host}/live/{self._name}"
        self._stream_enabled = self._config["rtmp"]["enabled"]

        _LOGGER.debug("Adding camera: %s", name)

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._name}_camera"

    @property
    def name(self):
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
    def available(self) -> bool:
        """Return the availability of the camera."""
        return True

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


class FrigateMqttSnapshots(Camera):
    """Frigate best camera class."""

    def __init__(self, config_entry, frigate_config, cam_name, obj_name):
        """Construct a FrigateMqttSnapshots camera."""
        super().__init__()

        self._config_entry = config_entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._last_image = None
        self._available = False
        self._sub_state = None
        self._topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/{self._obj_name}/snapshot"
        )
        self._availability_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}/available"
        )

    async def async_added_to_hass(self):
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""

        @callback
        def state_message_received(msg):
            """Handle a new received MQTT state message."""
            self._last_image = msg.payload
            self.async_write_ha_state()

        @callback
        def availability_message_received(msg):
            """Handle a new received MQTT availability message."""
            self._available = msg.payload == "online"
            self.async_write_ha_state()

        self._sub_state = await async_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": {
                    "topic": self._topic,
                    "msg_callback": state_message_received,
                    "qos": 0,
                    "encoding": None,
                },
                "availability_topic": {
                    "topic": self._availability_topic,
                    "msg_callback": availability_message_received,
                    "qos": 0,
                },
            },
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}_snapshot"

    @property
    def device_info(self):
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
    def name(self):
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._obj_name}".title()

    async def async_camera_image(self):
        """Return image response."""
        return self._last_image

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._available

    @property
    def state(self):
        """Return the camera state."""
        if self._last_image is None:
            return STATE_IDLE
        return STATE_DETECTED
