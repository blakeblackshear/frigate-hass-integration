"""Sensor platform for frigate."""
import logging
from .const import (
    DEFAULT_NAME, DOMAIN, PERSON_ICON, CAR_ICON, DOG_ICON, CAT_ICON,
    OTHER_ICON, ICON, SENSOR, NAME, VERSION, FPS, MS
)
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity
from homeassistant.components.mqtt.subscription import async_subscribe_topics

_LOGGER: logging.Logger = logging.getLogger(__package__)

CAMERA_FPS_TYPES = ['camera', 'detection', 'process', 'skipped']


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    devices = []
    for key, value in coordinator.data.items():
        if key == 'detection_fps':
            devices.append(FrigateFpsSensor(coordinator, entry))
        elif key == 'detectors':
            for name in value.keys():
                devices.append(DetectorSpeedSensor(coordinator, entry, name))
        elif key == 'service':
            # TODO: add sensors
            continue
        else:
            devices.extend([CameraFpsSensor(coordinator, entry, key, t) for t in CAMERA_FPS_TYPES])

    frigate_config = hass.data[DOMAIN]["config"]

    camera_objects = [(cam_name, obj) for cam_name, cam_config in frigate_config["cameras"].items() for obj in cam_config["objects"]["track"]]

    zone_objects = []
    for cam, obj in camera_objects:
        for zone_name in frigate_config["cameras"][cam]["zones"]:
            zone_objects.append((zone_name, obj))
    zone_objects = list(set(zone_objects))

    devices.extend([
        FrigateObjectCountSensor(hass, entry, frigate_config, cam_name, obj)
        for cam_name, obj in camera_objects + zone_objects
    ])

    async_add_devices(devices)


class FrigateFpsSensor(CoordinatorEntity):
    """Frigate Sensor class."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_detection_fps"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Detection Fps"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("detection_fps")
        else:
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
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.detector_name = detector_name

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.detector_name}_inference_speed"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        friendly_detector_name = self.detector_name.replace('_', ' ')
        return f"{friendly_detector_name} inference speed".title()

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data["detectors"][self.detector_name]["inference_speed"]
        else:
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
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        friendly_camera_name = self.camera_name.replace('_', ' ')
        return f"{friendly_camera_name} {self.fps_type} FPS".title()

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return FPS

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[self.camera_name][f"{self.fps_type}_fps"]
        else:
            return None

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return ICON


class FrigateObjectCountSensor(Entity):
    """Frigate Motion Sensor class."""

    def __init__(self, hass, entry, frigate_config, cam_name, obj_name):
        self.hass = hass
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._state = 0
        self._available = False
        self._sub_state = None
        self._topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._obj_name}"
        self._availability_topic = f"{self._frigate_config['mqtt']['topic_prefix']}/available"

        if self._obj_name == 'person':
            self._icon = PERSON_ICON
        elif self._obj_name == 'car':
            self._icon = CAR_ICON
        elif self._obj_name == 'dog':
            self._icon = DOG_ICON
        elif self._obj_name == 'cat':
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
                _LOGGER.info(f"Invalid payload received for {self.name}")
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
                }
            },
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        friendly_camera_name = self._cam_name.replace('_', ' ')
        return f"{friendly_camera_name} {self._obj_name}".title()

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
        return self._available
