"""Update platform for frigate."""
from __future__ import annotations

import logging

from homeassistant.components.update import UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    FrigateEntity,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import ATTR_COORDINATOR, DOMAIN, FRIGATE_RELEASE_TAG_URL, NAME

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Sensor entry setup."""
    coordinator = hass.data[DOMAIN][entry.entry_id][ATTR_COORDINATOR]

    entities = []
    entities.append(FrigateContainerUpdate(coordinator, entry))
    async_add_entities(entities)


class FrigateContainerUpdate(FrigateEntity, UpdateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate container update."""

    _attr_name = "Server"

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Construct a FrigateContainerUpdate."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "update", "frigate_server"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": NAME,
            "model": self._get_model(),
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def installed_version(self) -> str | None:
        """Version currently in use."""

        version_hash = self.coordinator.data.get("service", {}).get("version")

        if not version_hash:
            return None

        version = str(version_hash).split("-")[0]

        return version

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""

        version = self.coordinator.data.get("service", {}).get("latest_version")

        if not version or version == "unknown" or version == "disabled":
            return None

        return str(version)

    @property
    def release_url(self) -> str | None:
        """URL to the full release notes of the latest version available."""

        if (version := self.latest_version) is None:
            return None

        return f"{FRIGATE_RELEASE_TAG_URL}/v{version}"
