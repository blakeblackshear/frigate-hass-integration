"""Sensor platform for frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, PERCENTAGE, TEMP_CELSIUS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras,
    get_cameras_zones_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
    get_zones,
)
from .const import ATTR_CONFIG, ATTR_COORDINATOR, DOMAIN, FPS, MS, NAME
from .icons import ICON_CORAL, ICON_SERVER, ICON_SPEEDOMETER, get_icon_from_type

_LOGGER: logging.Logger = logging.getLogger(__name__)

CAMERA_FPS_TYPES = ["camera", "detection", "process", "skipped"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Sensor entry setup."""
    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]
    coordinator = hass.data[DOMAIN][entry.entry_id][ATTR_COORDINATOR]

    entities = []
    for key, value in coordinator.data.items():
        if key == "detection_fps":
            entities.append(FrigateFpsSensor(coordinator, entry))
        elif key == "detectors":
            for name in value.keys():
                entities.append(DetectorSpeedSensor(coordinator, entry, name))
        elif key == "gpu_usages":
            for name in value.keys():
                entities.append(GpuLoadSensor(coordinator, entry, name))
        elif key == "service":
            # Temperature is only supported on PCIe Coral.
            for name in value.get("temperatures", {}):
                entities.append(DeviceTempSensor(coordinator, entry, name))
        elif key == "cpu_usages":
            for camera in get_cameras(frigate_config):
                entities.append(
                    CameraProcessCpuSensor(coordinator, entry, camera, "capture")
                )
                entities.append(
                    CameraProcessCpuSensor(coordinator, entry, camera, "detect")
                )
                entities.append(
                    CameraProcessCpuSensor(coordinator, entry, camera, "ffmpeg")
                )
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
    entities.append(FrigateStatusSensor(coordinator, entry))
    async_add_entities(entities)


class FrigateFpsSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Sensor class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Detection fps"

    def __init__(
        self, coordinator: FrigateDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Construct a FrigateFpsSensor."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_entity_registry_enabled_default = False

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
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

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


class FrigateStatusSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Status Sensor class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Status"

    def __init__(
        self, coordinator: FrigateDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Construct a FrigateStatusSensor."""
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "sensor_status", "frigate"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return str(self.coordinator.server_status)

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_SERVER


class DetectorSpeedSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Detector Speed class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        self._attr_entity_registry_enabled_default = False

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
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._detector_name)} inference speed"

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


class GpuLoadSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate GPU Load class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        gpu_name: str,
    ) -> None:
        """Construct a GpuLoadSensor."""
        self._gpu_name = gpu_name
        self._attr_name = f"{get_friendly_name(self._gpu_name)} gpu load"
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "gpu_load", self._gpu_name
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def state(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            data = (
                self.coordinator.data.get("gpu_usages", {})
                .get(self._gpu_name, {})
                .get("gpu")
            )

            if data is None or not isinstance(data, str):
                return None

            try:
                return float(data.replace("%", "").strip())
            except ValueError:
                pass

        return None

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return "%"

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_SPEEDOMETER


class CameraFpsSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Camera Fps class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        self._attr_entity_registry_enabled_default = False

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
            "configuration_url": f"{self._config_entry.data.get(CONF_URL)}/cameras/{self._cam_name}",
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._fps_type} fps"

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
        self._frigate_config = frigate_config
        self._icon = get_icon_from_type(self._obj_name)

        super().__init__(
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/{self._obj_name}"
                    ),
                    "encoding": None,
                },
            },
        )

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        try:
            self._state = int(msg.payload)
            self.async_write_ha_state()
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
            "configuration_url": f"{self._config_entry.data.get(CONF_URL)}/cameras/{self._cam_name if self._cam_name not in get_zones(self._frigate_config) else ''}",
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._obj_name} count"

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


class DeviceTempSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Frigate Coral Temperature Sensor class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        name: str,
    ) -> None:
        """Construct a CoralTempSensor."""
        self._name = name
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id, "sensor_temp", self._name
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": self._get_model(),
            "configuration_url": self._config_entry.data.get(CONF_URL),
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._name)} temperature"

    @property
    def state(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            data = (
                self.coordinator.data.get("service", {})
                .get("temperatures", {})
                .get(self._name, 0.0)
            )
            try:
                return float(data)
            except (TypeError, ValueError):
                pass
        return None

    @property
    def unit_of_measurement(self) -> Any:
        """Return the unit of measurement of the sensor."""
        return TEMP_CELSIUS

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_CORAL


class CameraProcessCpuSensor(FrigateEntity, CoordinatorEntity):  # type: ignore[misc]
    """Cpu usage for camera processes class."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        cam_name: str,
        process_type: str,
    ) -> None:
        """Construct a CoralTempSensor."""
        self._cam_name = cam_name
        self._process_type = process_type
        self._attr_name = f"{self._process_type} cpu usage"
        FrigateEntity.__init__(self, config_entry)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            f"{self._process_type}_cpu_usage",
            self._cam_name,
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

    @property
    def state(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            pid_key = (
                "pid" if self._process_type == "detect" else f"{self._process_type}_pid"
            )
            pid = str(self.coordinator.data.get(self._cam_name, {}).get(pid_key, "-1"))
            data = (
                self.coordinator.data.get("cpu_usages", {})
                .get(pid, {})
                .get("cpu", None)
            )

            try:
                return float(data)
            except (TypeError, ValueError):
                pass
        return None

    @property
    def unit_of_measurement(self) -> Any:
        """Return the unit of measurement of the sensor."""
        return PERCENTAGE

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_CORAL
