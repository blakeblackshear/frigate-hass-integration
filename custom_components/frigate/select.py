"""Select platform for frigate."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.mqtt import async_publish
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateMQTTEntity,
    ReceiveMessage,
    decode_if_necessary,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
    verify_frigate_version,
)
from .const import ATTR_CONFIG, DOMAIN, NAME

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Select entry setup."""
    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    entities: list[SelectEntity] = []

    # Profile selector requires Frigate 0.18+
    if verify_frigate_version(frigate_config, "0.18"):
        profiles = frigate_config.get("profiles", {})
        if profiles:
            entities.append(FrigateProfileSelect(entry, frigate_config, profiles))

    async_add_entities(entities)


class FrigateProfileSelect(FrigateMQTTEntity, SelectEntity):
    """Frigate Profile Select class."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        profiles: dict[str, Any],
    ) -> None:
        """Construct a FrigateProfileSelect."""
        self._frigate_config = frigate_config
        self._profiles = profiles
        self._attr_options = list(profiles.keys())
        self._attr_current_option = None
        self._command_topic = f"{frigate_config['mqtt']['topic_prefix']}/profile/set"

        super().__init__(
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{frigate_config['mqtt']['topic_prefix']}/profile/state"
                    ),
                },
            },
        )

    @callback
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        payload = decode_if_necessary(msg.payload)
        if payload in self._attr_options:
            self._attr_current_option = payload
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "select",
            "profile",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Profile"

    @property
    def icon(self) -> str:
        """Return the icon of the entity."""
        return "mdi:home-account"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await async_publish(
            self.hass,
            self._command_topic,
            option,
            0,
            False,
        )
