"""
Custom integration to integrate frigate with Home Assistant.

For more details about this integration, please refer to
https://github.com/blakeblackshear/frigate-hass-integration
"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.mqtt.models import Message
from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .api import FrigateApiClient, FrigateApiClientError
from .const import DOMAIN, PLATFORMS, STARTUP_MESSAGE
from .views import ClipsProxyView, NotificationsProxyView, RecordingsProxyView

SCAN_INTERVAL = timedelta(seconds=5)

_LOGGER: logging.Logger = logging.getLogger(__name__)


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


def get_cameras_and_objects(config: dict[str, Any]) -> {(str, str)}:
    """Get cameras and tracking object tuples."""
    camera_objects = set()
    for cam_name, cam_config in config["cameras"].items():
        for obj in cam_config["objects"]["track"]:
            camera_objects.add((cam_name, obj))
    return camera_objects


def get_cameras_zones_and_objects(config: dict[str, Any]) -> {(str, str)}:
    """Get cameras/zones and tracking object tuples."""
    camera_objects = get_cameras_and_objects(config)

    zone_objects = set()
    for cam_name, obj in camera_objects:
        for zone_name in config["cameras"][cam_name]["zones"]:
            zone_objects.add((zone_name, obj))
    return camera_objects.union(zone_objects)


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
    hass.http.register_view(ClipsProxyView(frigate_host, websession))
    hass.http.register_view(RecordingsProxyView(frigate_host, websession))
    hass.http.register_view(NotificationsProxyView(frigate_host, websession))

    # setup api polling
    session = async_get_clientsession(hass)
    client = FrigateApiClient(frigate_host, session)

    # start the coordinator
    coordinator = FrigateDataUpdateCoordinator(hass, client=client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        config = await client.async_get_config()
    except FrigateApiClientError as exc:
        raise ConfigEntryNotReady from exc

    hass.data[DOMAIN]["config"] = config

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    entry.add_update_listener(_async_entry_updated)
    return True


class FrigateDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: FrigateApiClient):
        """Initialize."""
        self._api = client
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            return await self._api.async_get_stats()
        except FrigateApiClientError as exc:
            raise UpdateFailed from exc


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


class FrigateEntity(Entity):
    """Base class for Frigate entities."""

    def __init__(self, config_entry: str):
        """Construct a FrigateEntity."""
        Entity.__init__(self)

        self._config_entry = config_entry
        self._available = True

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        return self._available


class FrigateMQTTEntity(FrigateEntity):
    """Base class for MQTT-based Frigate entities."""

    def __init__(
        self,
        config_entry,
        frigate_config: dict[str, Any],
        state_topic_config: dict[str, Any],
    ) -> None:
        """Construct a FrigateMQTTEntity."""
        super().__init__(config_entry)
        self._frigate_config = frigate_config
        self._sub_state = None
        self._available = False
        self._state_topic_config = {
            "msg_callback": self._state_message_received,
            "qos": 0,
            **state_topic_config,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe mqtt events."""
        self._sub_state = await async_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": self._state_topic_config,
                "availability_topic": {
                    "topic": f"{self._frigate_config['mqtt']['topic_prefix']}/available",
                    "msg_callback": self._availability_message_received,
                    "qos": 0,
                },
            },
        )

    @callback
    def _state_message_received(self, msg: Message) -> None:
        """State message received."""
        self.async_write_ha_state()

    @callback
    def _availability_message_received(self, msg: Message) -> None:
        """Handle a new received MQTT availability message."""
        self._available = msg.payload == "online"
        self.async_write_ha_state()
