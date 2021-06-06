"""Sensor platform for frigate."""
import logging

from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import get_friendly_name, get_frigate_device_identifier
from .const import (
    CAR_ICON,
    CAT_ICON,
    DOG_ICON,
    DOMAIN,
    FPS,
    ICON,
    MS,
    NAME,
    OTHER_ICON,
    PERSON_ICON,
    VERSION,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)

CAMERA_FPS_TYPES = ["camera", "detection", "process", "skipped"]


async def async_setup_entry(hass, entry, async_add_devices):
    """Sensor entry setup."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    devices = []
    for key, value in coordinator.data.items():
        if key == "detection_fps":
            devices.append(FrigateFpsSensor(coordinator, entry))
        elif key == "detectors":
            for name in value.keys():
                devices.append(DetectorSpeedSensor(coordinator, entry, name))
        elif key == "service":
            # TODO: add sensors
            continue
        else:
            devices.extend(
                [CameraFpsSensor(coordinator, entry, key, t) for t in CAMERA_FPS_TYPES]
            )

    frigate_config = hass.data[DOMAIN]["config"]

    camera_objects = [
        (cam_name, obj)
        for cam_name, cam_config in frigate_config["cameras"].items()
        for obj in cam_config["objects"]["track"]
    ]

    zone_objects = []
    for cam, obj in camera_objects:
        for zone_name in frigate_config["cameras"][cam]["zones"]:
            zone_objects.append((zone_name, obj))
    zone_objects = list(set(zone_objects))

    devices.extend(
        [
            FrigateObjectCountSensor(hass, entry, frigate_config, cam_name, obj)
            for cam_name, obj in camera_objects + zone_objects
        ]
    )

    async_add_devices(devices)


class FrigateFpsSensor(CoordinatorEntity):
    """Frigate Sensor class."""

    def __init__(self, coordinator, config_entry) -> None:
        """Construct a FrigateFpsSensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_detection_fps"

    @property
    def device_info(self):
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self.config_entry)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Detection Fps"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(self.coordinator.data.get("detection_fps"))
        return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return ICON


class DetectorSpeedSensor(CoordinatorEntity):
    """Frigate Detector Speed class."""

    def __init__(self, coordinator, config_entry, detector_name):
        """Construct a DetectorSpeedSensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.detector_name = detector_name

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.detector_name}_inference_speed"

    @property
    def device_info(self):
        """Get device information."""
        return {
            "identifiers": {get_frigate_device_identifier(self.config_entry)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{get_friendly_name(self.detector_name)} inference speed".title()

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(
                self.coordinator.data["detectors"][self.detector_name][
                    "inference_speed"
                ]
            )
        return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return MS

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return ICON


class CameraFpsSensor(CoordinatorEntity):
    """Frigate Camera Fps class."""

    def __init__(self, coordinator, config_entry, camera_name, fps_type):
        """Construct a CameraFpsSensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.camera_name = camera_name
        self.fps_type = fps_type

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.camera_name}_{self.fps_type}_fps"

    @property
    def device_info(self):
        """Get device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self.config_entry, self.camera_name)
            },
            "via_device": get_frigate_device_identifier(self.config_entry),
            "name": get_friendly_name(self.camera_name),
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{get_friendly_name(self.camera_name)} {self.fps_type} FPS".title()

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(
                self.coordinator.data[self.camera_name][f"{self.fps_type}_fps"]
            )
        return None

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return ICON


class FrigateObjectCountSensor(Entity):
    """Frigate Motion Sensor class."""

    def __init__(self, hass, entry, frigate_config, cam_name, obj_name):
        """Construct a FrigateObjectCountSensor."""
        self.hass = hass
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._state = 0
        self._available = False
        self._sub_state = None
        self._topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._obj_name}"
        self._availability_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}/available"
        )

        if self._obj_name == "person":
            self._icon = PERSON_ICON
        elif self._obj_name == "car":
            self._icon = CAR_ICON
        elif self._obj_name == "dog":
            self._icon = DOG_ICON
        elif self._obj_name == "cat":
            self._icon = CAT_ICON
        else:
            self._icon = OTHER_ICON

    async def async_added_to_hass(self):
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""

        @callback
        def state_message_received(msg):
            """Handle a new received MQTT state message."""
            self._state = msg.payload

            self.async_write_ha_state()

        @callback
        def availability_message_received(msg):
            """Handle a new received MQTT availability message."""
            payload = msg.payload

            if payload == "online":
                self._available = True
            elif payload == "offline":
                self._available = False
            else:
                _LOGGER.info("Invalid payload received for: %s", self.name)
                return

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
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}"

    @property
    def device_info(self):
        """Get device information."""

        return {
            "identifiers": {get_frigate_device_identifier(self._entry, self._cam_name)},
            "via_device": get_frigate_device_identifier(self._entry),
            "name": get_friendly_name(self._cam_name),
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._obj_name}".title()

    @property
    def state(self):
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return "objects"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._available
