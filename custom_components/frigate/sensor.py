"""Sensor platform for frigate."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.mqtt.models import Message
from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    FrigateDataUpdateCoordinator,
    get_cameras_zones_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
)
from .const import (
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
    VERSION,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)

CAMERA_FPS_TYPES = ["camera", "detection", "process", "skipped"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Sensor entry setup."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

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

    frigate_config = hass.data[DOMAIN]["config"]
    entities.extend(
        [
            FrigateObjectCountSensor(entry, frigate_config, cam_name, obj)
            for cam_name, obj in get_cameras_zones_and_objects(frigate_config)
        ]
    )
    async_add_entities(entities)


class FrigateFpsSensor(CoordinatorEntity):
    """Frigate Sensor class."""

    def __init__(
        self, coordinator: FrigateDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Construct a FrigateFpsSensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_detection_fps"

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": VERSION,
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


class DetectorSpeedSensor(CoordinatorEntity):
    """Frigate Detector Speed class."""

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        detector_name: str,
    ) -> None:
        """Construct a DetectorSpeedSensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._detector_name = detector_name

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._detector_name}_inference_speed"

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self._config_entry)},
            "name": NAME,
            "model": VERSION,
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


class CameraFpsSensor(CoordinatorEntity):
    """Frigate Camera Fps class."""

    def __init__(
        self,
        coordinator: FrigateDataUpdateCoordinator,
        config_entry: ConfigEntry,
        camera_name: str,
        fps_type: str,
    ) -> None:
        """Construct a CameraFpsSensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._camera_name = camera_name
        self._fps_type = fps_type

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._camera_name}_{self._fps_type}_fps"

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._camera_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._camera_name),
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._camera_name)} {self._fps_type} FPS".title()

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def state(self) -> int | None:
        """Return the state of the sensor."""

        if self.coordinator.data:
            data = self.coordinator.data.get(self._camera_name, {}).get(
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


class FrigateObjectCountSensor(Entity):
    """Frigate Motion Sensor class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateObjectCountSensor."""
        self._config_entry = config_entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._state = 0
        self._available = False
        self._sub_state = None
        self._topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/{self._obj_name}"
        )
        self._availability_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}/available"
        )

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

    async def async_added_to_hass(self) -> None:
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""

        @callback
        def state_message_received(msg: Message) -> None:
            """Handle a new received MQTT state message."""
            try:
                self._state = int(msg.payload)
                self.async_write_ha_state()
            except ValueError:
                pass

        @callback
        def availability_message_received(msg: Message) -> None:
            """Handle a new received MQTT availability message."""
            self._available = msg.payload == "online"
            self.async_write_ha_state()

        self._sub_state = await async_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": {
                    "topic": self._topic,
                    "msg_callback": state_message_received,
                    "qos": 0,
                },
                "availability_topic": {
                    "topic": self._availability_topic,
                    "msg_callback": availability_message_received,
                    "qos": 0,
                },
            },
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""

        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": VERSION,
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

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._available
