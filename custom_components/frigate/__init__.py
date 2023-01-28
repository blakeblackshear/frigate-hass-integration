"""
Custom integration to integrate frigate with Home Assistant.

For more details about this integration, please refer to
https://github.com/blakeblackshear/frigate-hass-integration
"""
from __future__ import annotations

from datetime import timedelta
import logging
import re
from typing import Any, Callable, Final

from awesomeversion import AwesomeVersion

from custom_components.frigate.config_flow import get_config_entry_title
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_MODEL, CONF_HOST, CONF_URL
from homeassistant.core import Config, HomeAssistant, callback, valid_entity_id
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration
from homeassistant.util import slugify

from .api import FrigateApiClient, FrigateApiClientError
from .const import (
    ATTR_CLIENT,
    ATTR_CONFIG,
    ATTR_COORDINATOR,
    CONF_CAMERA_STATIC_IMAGE_HEIGHT,
    DOMAIN,
    FRIGATE_RELEASES_URL,
    FRIGATE_VERSION_ERROR_CUTOFF,
    NAME,
    PLATFORMS,
    STARTUP_MESSAGE,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_STARTING,
)
from .views import async_setup as views_async_setup
from .ws_api import async_setup as ws_api_async_setup

SCAN_INTERVAL = timedelta(seconds=5)

_LOGGER: logging.Logger = logging.getLogger(__name__)


# Typing notes:
# - The HomeAssistant library does not provide usable type hints for custom
#   components. Certain type checks (e.g. decorators and class inheritance) need
#   to be marked as ignored or casted, when using the default Home Assistant
#   mypy settings. Using the same settings is preferable, to smoothen a future
#   migration to Home Assistant Core.


def get_frigate_device_identifier(
    entry: ConfigEntry, camera_name: str | None = None
) -> tuple[str, str]:
    """Get a device identifier."""
    if camera_name:
        return (DOMAIN, f"{entry.entry_id}:{slugify(camera_name)}")
    else:
        return (DOMAIN, entry.entry_id)


def get_frigate_entity_unique_id(
    config_entry_id: str, type_name: str, name: str
) -> str:
    """Get the unique_id for a Frigate entity."""
    return f"{config_entry_id}:{type_name}:{name}"


def get_friendly_name(name: str) -> str:
    """Get a friendly version of a name."""
    return name.replace("_", " ").title()


def get_cameras(config: dict[str, Any]) -> set[str]:
    """Get cameras."""
    cameras = set()

    for cam_name, _ in config["cameras"].items():
        cameras.add(cam_name)

    return cameras


def get_cameras_and_objects(
    config: dict[str, Any], include_all: bool = True
) -> set[tuple[str, str]]:
    """Get cameras and tracking object tuples."""
    camera_objects = set()
    for cam_name, cam_config in config["cameras"].items():
        for obj in cam_config["objects"]["track"]:
            camera_objects.add((cam_name, obj))

        # add an artificial all label to track
        # all objects for this camera
        if include_all:
            camera_objects.add((cam_name, "all"))

    return camera_objects


def get_cameras_zones_and_objects(config: dict[str, Any]) -> set[tuple[str, str]]:
    """Get cameras/zones and tracking object tuples."""
    camera_objects = get_cameras_and_objects(config)

    zone_objects = set()
    for cam_name, obj in camera_objects:
        for zone_name in config["cameras"][cam_name]["zones"]:
            zone_name_objects = config["cameras"][cam_name]["zones"][zone_name].get(
                "objects"
            )
            if not zone_name_objects or obj in zone_name_objects:
                zone_objects.add((zone_name, obj))

            # add an artificial all label to track
            # all objects for this zone
            zone_objects.add((zone_name, "all"))
    return camera_objects.union(zone_objects)


def get_cameras_and_zones(config: dict[str, Any]) -> set[str]:
    """Get cameras and zones."""
    cameras_zones = set()
    for camera in config.get("cameras", {}).keys():
        cameras_zones.add(camera)
        for zone in config["cameras"][camera].get("zones", {}).keys():
            cameras_zones.add(zone)
    return cameras_zones


def get_zones(config: dict[str, Any]) -> set[str]:
    """Get zones."""
    cameras_zones = set()
    for camera in config.get("cameras", {}).keys():
        for zone in config["cameras"][camera].get("zones", {}).keys():
            cameras_zones.add(zone)
    return cameras_zones


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up this integration using YAML is not supported."""
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(
        STARTUP_MESSAGE.format(
            title=NAME,
            integration_version=integration.version,
        )
    )

    hass.data.setdefault(DOMAIN, {})

    ws_api_async_setup(hass)
    views_async_setup(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    client = FrigateApiClient(
        entry.data.get(CONF_URL),
        async_get_clientsession(hass),
    )
    coordinator = FrigateDataUpdateCoordinator(hass, client=client)
    await coordinator.async_config_entry_first_refresh()

    try:
        server_version = await client.async_get_version()
        config = await client.async_get_config()
    except FrigateApiClientError as exc:
        raise ConfigEntryNotReady from exc

    if AwesomeVersion(server_version) <= AwesomeVersion(FRIGATE_VERSION_ERROR_CUTOFF):
        _LOGGER.error(
            "Using a Frigate server (%s) with version %s <= %s which is not "
            "compatible -- you must upgrade: %s",
            entry.data[CONF_URL],
            server_version,
            FRIGATE_VERSION_ERROR_CUTOFF,
            FRIGATE_RELEASES_URL,
        )
        return False

    model = f"{(await async_get_integration(hass, DOMAIN)).version}/{server_version}"

    hass.data[DOMAIN][entry.entry_id] = {
        ATTR_COORDINATOR: coordinator,
        ATTR_CLIENT: client,
        ATTR_CONFIG: config,
        ATTR_MODEL: model,
    }

    # Remove old devices associated with cameras that have since been removed
    # from the Frigate server, keeping the 'master' device for this config
    # entry.
    current_devices: set[tuple[str, str]] = set({get_frigate_device_identifier(entry)})
    for item in get_cameras_and_zones(config):
        current_devices.add(get_frigate_device_identifier(entry, item))

    if config.get("birdseye", {}).get("restream", False):
        current_devices.add(get_frigate_device_identifier(entry, "birdseye"))

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        for identifier in device_entry.identifiers:
            if identifier in current_devices:
                break
        else:
            device_registry.async_remove_device(device_entry.id)

    # Cleanup old clips switch (<v0.9.0) if it exists.
    entity_registry = er.async_get(hass)
    for camera in config["cameras"].keys():
        unique_id = get_frigate_entity_unique_id(
            entry.entry_id, SWITCH_DOMAIN, f"{camera}_clips"
        )
        entity_id = entity_registry.async_get_entity_id(
            SWITCH_DOMAIN, DOMAIN, unique_id
        )
        if entity_id:
            entity_registry.async_remove(entity_id)

    # Remove old `camera_image_height` option.
    if CONF_CAMERA_STATIC_IMAGE_HEIGHT in entry.options:
        new_options = entry.options.copy()
        new_options.pop(CONF_CAMERA_STATIC_IMAGE_HEIGHT)
        hass.config_entries.async_update_entry(entry, options=new_options)

    # Cleanup object_motion sensors (replaced with occupancy sensors).
    for cam_name, obj_name in get_cameras_zones_and_objects(config):
        unique_id = get_frigate_entity_unique_id(
            entry.entry_id,
            "motion_sensor",
            f"{cam_name}_{obj_name}",
        )
        entity_id = entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, unique_id
        )
        if entity_id:
            entity_registry.async_remove(entity_id)

    # Rename / change ID of object count sensors.
    for cam_name, obj_name in get_cameras_zones_and_objects(config):
        unique_id = get_frigate_entity_unique_id(
            entry.entry_id,
            "sensor_object_count",
            f"{cam_name}_{obj_name}",
        )
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        new_id = f"sensor.{slugify(cam_name)}_{slugify(obj_name)}_count"

        if (
            entity_id
            and entity_id != new_id
            and valid_entity_id(new_id)
            and not entity_registry.async_get(new_id)
        ):
            new_name = f"{get_friendly_name(cam_name)} {obj_name} Count".title()
            entity_registry.async_update_entity(
                entity_id=entity_id,
                new_entity_id=new_id,
                name=new_name,
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


class FrigateDataUpdateCoordinator(DataUpdateCoordinator):  # type: ignore[misc]
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: FrigateApiClient):
        """Initialize."""
        self._api = client
        self.server_status: str = STATUS_STARTING
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            stats = await self._api.async_get_stats()
            self.server_status = STATUS_RUNNING
            return stats
        except FrigateApiClientError as exc:
            self.server_status = STATUS_ERROR
            raise UpdateFailed from exc


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unload_ok = bool(
        await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def _async_entry_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle entry updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate from v1 entry."""

    if config_entry.version == 1:
        _LOGGER.debug("Migrating config entry from version '%s'", config_entry.version)

        data = {**config_entry.data}
        data[CONF_URL] = data.pop(CONF_HOST)
        hass.config_entries.async_update_entry(
            config_entry, data=data, title=get_config_entry_title(data[CONF_URL])
        )
        config_entry.version = 2

        @callback  # type: ignore[misc]
        def update_unique_id(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
            """Update unique ID of entity entry."""

            converters: Final[dict[re.Pattern, Callable[[re.Match], list[str]]]] = {
                re.compile(rf"^{DOMAIN}_(?P<cam_obj>\S+)_binary_sensor$"): lambda m: [
                    "occupancy_sensor",
                    m.group("cam_obj"),
                ],
                re.compile(rf"^{DOMAIN}_(?P<cam>\S+)_camera$"): lambda m: [
                    "camera",
                    m.group("cam"),
                ],
                re.compile(rf"^{DOMAIN}_(?P<cam_obj>\S+)_snapshot$"): lambda m: [
                    "camera_snapshots",
                    m.group("cam_obj"),
                ],
                re.compile(rf"^{DOMAIN}_detection_fps$"): lambda m: [
                    "sensor_fps",
                    "detection",
                ],
                re.compile(
                    rf"^{DOMAIN}_(?P<detector>\S+)_inference_speed$"
                ): lambda m: ["sensor_detector_speed", m.group("detector")],
                re.compile(rf"^{DOMAIN}_(?P<cam_fps>\S+)_fps$"): lambda m: [
                    "sensor_fps",
                    m.group("cam_fps"),
                ],
                re.compile(rf"^{DOMAIN}_(?P<cam_switch>\S+)_switch$"): lambda m: [
                    "switch",
                    m.group("cam_switch"),
                ],
                # Caution: This is a broad but necessary match (keep until last).
                re.compile(rf"^{DOMAIN}_(?P<cam_obj>\S+)$"): lambda m: [
                    "sensor_object_count",
                    m.group("cam_obj"),
                ],
            }

            for regexp, func in converters.items():
                match = regexp.match(entity_entry.unique_id)
                if match:
                    args = [config_entry.entry_id] + func(match)
                    return {"new_unique_id": get_frigate_entity_unique_id(*args)}
            return None

        await er.async_migrate_entries(hass, config_entry.entry_id, update_unique_id)
        _LOGGER.debug(
            "Migrating config entry to version '%s' successful", config_entry.version
        )

    return True


class FrigateEntity(Entity):  # type: ignore[misc]
    """Base class for Frigate entities."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: ConfigEntry):
        """Construct a FrigateEntity."""
        Entity.__init__(self)

        self._config_entry = config_entry
        self._available = True

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        return self._available

    def _get_model(self) -> str:
        """Get the Frigate device model string."""
        return str(self.hass.data[DOMAIN][self._config_entry.entry_id][ATTR_MODEL])


class FrigateMQTTEntity(FrigateEntity):
    """Base class for MQTT-based Frigate entities."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        topic_map: dict[str, Any],
    ) -> None:
        """Construct a FrigateMQTTEntity."""
        super().__init__(config_entry)
        self._frigate_config = frigate_config
        self._sub_state = None
        self._available = False
        self._topic_map = topic_map

    async def async_added_to_hass(self) -> None:
        """Subscribe mqtt events."""
        self._topic_map["availability_topic"] = {
            "topic": f"{self._frigate_config['mqtt']['topic_prefix']}/available",
            "msg_callback": self._availability_message_received,
            "qos": 0,
        }

        state = async_prepare_subscribe_topics(
            self.hass,
            self._sub_state,
            self._topic_map,
        )
        self._sub_state = await async_subscribe_topics(self.hass, state)

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup prior to hass removal."""
        async_unsubscribe_topics(self.hass, self._sub_state)
        self._sub_state = None

    @callback  # type: ignore[misc]
    def _availability_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT availability message."""
        self._available = msg.payload == "online"
        self.async_write_ha_state()
