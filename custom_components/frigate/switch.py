"""Sensor platform for frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.mqtt import async_publish
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateMQTTEntity,
    ReceiveMessage,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CONFIG,
    DOMAIN,
    ICON_FILM_MULTIPLE,
    ICON_IMAGE_MULTIPLE,
    ICON_MOTION_SENSOR,
    NAME,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Switch entry setup."""
    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    entities = []
    for camera in frigate_config["cameras"].keys():
        entities.extend(
            [
                FrigateSwitch(entry, frigate_config, camera, "detect"),
                FrigateSwitch(entry, frigate_config, camera, "recordings"),
                FrigateSwitch(entry, frigate_config, camera, "snapshots"),
            ]
        )
    async_add_entities(entities)


class FrigateSwitch(FrigateMQTTEntity, SwitchEntity):  # type: ignore[misc]
    """Frigate Switch class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        switch_name: str,
    ) -> None:
        """Construct a FrigateSwitch."""

        self._cam_name = cam_name
        self._switch_name = switch_name
        self._is_on = False
        self._command_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/{self._switch_name}/set"
        )

        if self._switch_name == "snapshots":
            self._icon = ICON_IMAGE_MULTIPLE
        elif self._switch_name == "recordings":
            self._icon = ICON_FILM_MULTIPLE
        else:
            self._icon = ICON_MOTION_SENSOR

        super().__init__(
            config_entry,
            frigate_config,
            {
                "topic": (
                    f"{frigate_config['mqtt']['topic_prefix']}"
                    f"/{self._cam_name}/{self._switch_name}/state"
                )
            },
        )

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._is_on = msg.payload == "ON"
        super()._state_message_received(msg)

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "switch",
            f"{self._cam_name}_{self._switch_name}",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": self._get_model(),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._switch_name}".title()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await async_publish(
            self.hass,
            self._command_topic,
            "ON",
            0,
            False,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await async_publish(
            self.hass,
            self._command_topic,
            "OFF",
            0,
            False,
        )

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return self._icon
