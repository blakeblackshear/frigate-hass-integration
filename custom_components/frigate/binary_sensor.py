"""Binary sensor platform for Frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_MOTION,
    BinarySensorEntity,
)
from homeassistant.components.mqtt.models import Message
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateMQTTEntity,
    get_cameras_zones_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
)
from .const import DOMAIN, NAME, VERSION

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Binary sensor entry setup."""
    frigate_config = hass.data[DOMAIN]["config"]
    async_add_entities(
        [
            FrigateMotionSensor(entry, frigate_config, cam_name, obj)
            for cam_name, obj in get_cameras_zones_and_objects(frigate_config)
        ]
    )


class FrigateMotionSensor(FrigateMQTTEntity, BinarySensorEntity):
    """Frigate Motion Sensor class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a new FrigateMotionSensor."""
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._is_on = False

        super().__init__(
            config_entry,
            frigate_config,
            {
                "topic": (
                    f"{frigate_config['mqtt']['topic_prefix']}"
                    f"/{self._cam_name}/{self._obj_name}"
                )
            },
        )

    @callback
    def _state_message_received(self, msg: Message) -> None:
        """Handle a new received MQTT state message."""
        try:
            self._is_on = int(msg.payload) > 0
        except ValueError:
            self._is_on = False
        super()._state_message_received(msg)

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}_binary_sensor"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
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
        return f"{get_friendly_name(self._cam_name)} {self._obj_name} Motion".title()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def device_class(self) -> str:
        """Return the device class."""
        return DEVICE_CLASS_MOTION
