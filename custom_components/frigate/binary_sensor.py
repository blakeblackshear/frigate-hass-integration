"""Binary sensor platform for frigate."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_MOTION,
    BinarySensorEntity,
)
from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, NAME, VERSION

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: Callable
) -> None:
    """Setup sensor platform."""
    frigate_config = hass.data[DOMAIN]["config"]

    camera_objects = set()
    for cam_name, cam_config in frigate_config["cameras"].items():
        for obj in cam_config["objects"]["track"]:
            camera_objects.add((cam_name, obj))

    zone_objects = set()
    for cam, obj in camera_objects:
        for zone_name in frigate_config["cameras"][cam]["zones"]:
            zone_objects.add((zone_name, obj))

    async_add_devices([
        FrigateMotionSensor(hass, entry, frigate_config, cam_name, obj)
        for cam_name, obj in camera_objects.union(zone_objects)
    ])


class FrigateMotionSensor(BinarySensorEntity):
    """Frigate Motion Sensor class."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, frigate_config: dict[str, Any], cam_name: str, obj_name: str) -> None:
        """Construct a new FrigateMotionSensor."""
        self.hass = hass
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._is_on = False
        self._available = False
        self._sub_state = None
        self._topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._obj_name}"
        self._availability_topic = f"{self._frigate_config['mqtt']['topic_prefix']}/available"

    async def async_added_to_hass(self) -> None:
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""
        @callback
        def state_message_received(msg: str) -> None:
            """Handle a new received MQTT state message."""
            try:
                self._is_on = int(msg.payload) > 0
            except ValueError:
                self._is_on = False
            self.async_write_ha_state()

        @callback
        def availability_message_received(msg: str) -> None:
            """Handle a new received MQTT availability message."""
            payload = msg.payload
            self._available = (payload == "online")
            self.async_write_ha_state()

        self._sub_state = await async_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": {
                    "topic": self._topic,
                    "msg_callback": state_message_received,
                    "qos": 0,
                },
                "availability_topic": {
                    "topic": self._availability_topic,
                    "msg_callback": availability_message_received,
                    "qos": 0,
                }
            },
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}_binary_sensor"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        friendly_camera_name = self._cam_name.replace('_', ' ')
        return f"{friendly_camera_name} {self._obj_name} Motion".title()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def device_class(self) -> str:
        """Return the device class."""
        return DEVICE_CLASS_MOTION

    @property
    def available(self) -> bool:
        """Return true if the binary sensor is available."""
        return self._available
