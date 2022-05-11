"""Diagnostics support for Frigate."""

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_CONFIG, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = {
        "frigate_config": hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG],
    }
    return data
