"""Sensor platform for frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras_zones_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CONFIG,
    ATTR_COORDINATOR,
    DOMAIN,
    FPS,
    ICON_CAR,
    ICON_CAT,
    ICON_DOG,
    ICON_OTHER,
    ICON_PERSON,
    ICON_SPEEDOMETER,
    MS,
    NAME,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

CAMERA_FPS_TYPES = ["camera", "detection", "process", "skipped"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Sensor entry setup."""
    coordinator = hass.data[DOMAIN][entry.entry_id][ATTR_COORDINATOR]

    entities = []
    for key, value in coordinator.data.items():
        if key == "detection_fps":
            entities.append(FrigateFpsSensor(coordinator, entry))
        elif key == "detectors":
            for name in value.keys():
                entities.append(DetectorSpeedSensor(coordinator, entry, name))
        elif key == "service":
            # Media storage statistics, uptime and Frigate version. For now,
            # these do not feature in entities.
            continue
        else:
            entities.extend(
                [CameraFpsSensor(coordinator, entry, key, t) for t in CAMERA_FPS_TYPES]
            )

    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    entities.extend(
        [
            FrigateObjectCountSensor(entry, frigate_config, cam_name, obj)
            for cam_name, obj in get_cameras_zones_and_objects(frigate_config)
        ]
    )
    async_add_entities(entities)


class FrigateFpsSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Sensor class."""

    def __init__(
        self, coordinator: FrigateDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Construct a FrigateFpsSensor."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "sensor_fps", "detection"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Detection Fps"

    @property
    def state(self) -> int | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            data = self.coordinator.data.get("detection_fps")
            if data is not None:
                try:
                    return round(float(data))
                except ValueError:
                    pass
        return None

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_SPEEDOMETER


class DetectorSpeedSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Detector Speed class."""

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        detector_name: str,
    ) -> None:
        """Construct a DetectorSpeedSensor."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._detector_name = detector_name

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "sensor_detector_speed", self._detector_name
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._detector_name)} inference speed".title()

    @property
    def state(self) -> int | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            data = (
                self.coordinator.data.get("detectors", {})
                .get(self._detector_name, {})
                .get("inference_speed")
            )
            if data is not None:
                try:
                    return round(float(data))
                except ValueError:
                    pass
        return None

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return MS

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_SPEEDOMETER


class CameraFpsSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Camera Fps class."""

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        cam_name: str,
        fps_type: str,
    ) -> None:
        """Construct a CameraFpsSensor."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._cam_name = cam_name
        self._fps_type = fps_type

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "sensor_fps",
            f"{self._cam_name}_{self._fps_type}",
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
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._fps_type} FPS".title()

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def state(self) -> int | None:
        """Return the state of the sensor."""

        if self.coordinator.data:
            data = self.coordinator.data.get(self._cam_name, {}).get(
                f"{self._fps_type}_fps"
            )
            if data is not None:
                try:
                    return round(float(data))
                except ValueError:
                    pass
        return None

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_SPEEDOMETER


class FrigateObjectCountSensor(FrigateMQTTEntity):
    """Frigate Motion Sensor class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateObjectCountSensor."""
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._state = 0

        if self._obj_name == "person":
            self._icon = ICON_PERSON
        elif self._obj_name == "car":
            self._icon = ICON_CAR
        elif self._obj_name == "dog":
            self._icon = ICON_DOG
        elif self._obj_name == "cat":
            self._icon = ICON_CAT
        else:
            self._icon = ICON_OTHER

        super().__init__(
            config_entry,
            frigate_config,
            {
                "topic": (
                    f"{frigate_config['mqtt']['topic_prefix']}"
                    f"/{self._cam_name}/{self._obj_name}"
                )
            },
        )

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        try:
            self._state = int(msg.payload)
            super()._state_message_received(msg)
        except ValueError:
            pass

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "sensor_object_count",
            f"{self._cam_name}_{self._obj_name}",
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
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._obj_name}".title()

    @property
    def state(self) -> int:
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return "objects"

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return self._icon
