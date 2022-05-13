"""Diagnostics support for Frigate."""

from typing import Any, Dict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_CLIENT, ATTR_CONFIG, CONF_PASSWORD, CONF_PATH, DOMAIN

REDACT_CONFIG = {CONF_PASSWORD, CONF_PATH}


def get_redacted_data(data: Dict[str, Any]) -> Any:
    """Redact sensitive vales from data."""
    return async_redact_data(data, REDACT_CONFIG)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""

    config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    redacted_config = get_redacted_data(config)

    stats = await hass.data[DOMAIN][entry.entry_id][ATTR_CLIENT].async_get_stats()
    redacted_stats = get_redacted_data(stats)

    data = {
        "frigate_config": redacted_config,
        "frigate_stats": redacted_stats,
    }
    return data
