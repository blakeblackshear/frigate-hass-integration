"""Number platform for frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.mqtt import async_publish
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CONFIG,
    DOMAIN,
    MAX_CONTOUR_AREA,
    MAX_THRESHOLD,
    MIN_CONTOUR_AREA,
    MIN_THRESHOLD,
    NAME,
)
from .icons import ICON_SPEEDOMETER

_LOGGER: logging.Logger = logging.getLogger(__name__)

CAMERA_FPS_TYPES = ["camera", "detection", "process", "skipped"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Sensor entry setup."""
    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    entities = []

    # add motion configurations for cameras
    for cam_name in get_cameras(frigate_config):
        entities.extend(
            [FrigateMotionContourArea(entry, frigate_config, cam_name, False)]
        )
        entities.extend(
            [FrigateMotionThreshold(entry, frigate_config, cam_name, False)]
        )

    async_add_entities(entities)


class FrigateMotionContourArea(FrigateMQTTEntity, NumberEntity):  # type: ignore[misc]
    """FrigateMotionContourArea class."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Contour area"
    _attr_native_min_value = MIN_CONTOUR_AREA
    _attr_native_max_value = MAX_CONTOUR_AREA
    _attr_native_step = 1

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        default_enabled: bool,
    ) -> None:
        """Construct a FrigateNumber."""
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._attr_native_value = float(
            self._frigate_config["cameras"][self._cam_name]["motion"]["contour_area"]
        )
        self._command_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/motion_contour_area/set"
        )

        self._attr_entity_registry_enabled_default = default_enabled

        super().__init__(
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/motion_contour_area/state"
                    ),
                },
            },
        )

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        try:
            self._attr_native_value = float(msg.payload)
        except (TypeError, ValueError):
            pass

        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "number",
            f"{self._cam_name}_contour_area",
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
            "configuration_url": f"{self._config_entry.data.get(CONF_URL)}/cameras/{self._cam_name}",
            "manufacturer": NAME,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update motion contour area."""
        await async_publish(
            self.hass,
            self._command_topic,
            int(value),
            0,
            False,
        )

    @property
    def icon(self) -> str:
        """Return the icon of the number."""
        return ICON_SPEEDOMETER


class FrigateMotionThreshold(FrigateMQTTEntity, NumberEntity):  # type: ignore[misc]
    """FrigateMotionThreshold class."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Threshold"
    _attr_native_min_value = MIN_THRESHOLD
    _attr_native_max_value = MAX_THRESHOLD
    _attr_native_step = 1

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        default_enabled: bool,
    ) -> None:
        """Construct a FrigateMotionThreshold."""
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._attr_native_value = float(
            self._frigate_config["cameras"][self._cam_name]["motion"]["threshold"]
        )
        self._command_topic = (
            f"{frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/motion_threshold/set"
        )

        self._attr_entity_registry_enabled_default = default_enabled

        super().__init__(
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/motion_threshold/state"
                    ),
                },
            },
        )

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        try:
            self._attr_native_value = float(msg.payload)
        except (TypeError, ValueError):
            pass

        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "number",
            f"{self._cam_name}_threshold",
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
            "configuration_url": f"{self._config_entry.data.get(CONF_URL)}/cameras/{self._cam_name}",
            "manufacturer": NAME,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update motion threshold."""
        await async_publish(
            self.hass,
            self._command_topic,
            int(value),
            0,
            False,
        )

    @property
    def icon(self) -> str:
        """Return the icon of the number."""
        return ICON_SPEEDOMETER
