"""Diagnostics support for Frigate."""

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_CLIENT, ATTR_CONFIG, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    stats = await hass.data[DOMAIN][entry.entry_id][ATTR_CLIENT].async_get_stats()

    data = {"frigate_config": config, "frigate_stats": stats}
    return data
