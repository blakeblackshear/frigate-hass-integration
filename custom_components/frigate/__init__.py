"""
Custom integration to integrate frigate with Home Assistant.

For more details about this integration, please refer to
https://github.com/blakeblackshear/frigate-hass-integration
"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .api import FrigateApiClient
from .const import DOMAIN, PLATFORMS, STARTUP_MESSAGE
from .views import ClipsProxy, NotificationProxy, RecordingsProxy

SCAN_INTERVAL = timedelta(seconds=5)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def get_frigate_device_identifier(
    entry: ConfigEntry, camera_name: str | None = None
) -> tuple[str, str]:
    """Get a device identifier."""
    if camera_name:
        return (DOMAIN, f"{entry.entry_id}:{slugify(camera_name)}")
    else:
        return (DOMAIN, entry.entry_id)


def get_friendly_name(name: str) -> str:
    """Get a friendly version of a name."""
    return name.replace("_", " ").title()


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    frigate_host = hass.data[DOMAIN]["host"] = entry.data.get("host")

    # register views
    websession = hass.helpers.aiohttp_client.async_get_clientsession()
    hass.http.register_view(ClipsProxy(frigate_host, websession))
    hass.http.register_view(RecordingsProxy(frigate_host, websession))
    hass.http.register_view(NotificationProxy(frigate_host, websession))

    # setup api polling
    session = async_get_clientsession(hass)
    client = FrigateApiClient(frigate_host, session)

    # start the coordinator
    coordinator = FrigateDataUpdateCoordinator(hass, client=client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # get and store config info
    config = await client.async_get_config()
    hass.data[DOMAIN]["config"] = config

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    entry.add_update_listener(_async_entry_updated)
    return True


class FrigateDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: FrigateApiClient):
        """Initialize."""
        self._api: FrigateApiClient = client
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            return await self._api.async_get_stats()
        except Exception as exception:
            raise UpdateFailed() from exception


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def _async_entry_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle entry updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)
