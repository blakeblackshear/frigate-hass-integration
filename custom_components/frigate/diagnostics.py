"""Diagnostics support for Frigate."""

from typing import Any, Dict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_CLIENT, ATTR_CONFIG, CONF_PASSWORD, CONF_PATH, DOMAIN

REDACT_CONFIG = {CONF_PASSWORD, CONF_PATH}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""

    # get initial config
    config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    # get redacted config
    redacted_config = async_redact_data(config, REDACT_CONFIG)

    # get initial stats
    stats = await hass.data[DOMAIN][entry.entry_id][ATTR_CLIENT].async_get_stats()

    # get redacted stats
    redacted_stats = async_redact_data(stats, REDACT_CONFIG)

    data = {
        "frigate_config": redacted_config,
        "frigate_stats": redacted_stats,
    }
    return data
