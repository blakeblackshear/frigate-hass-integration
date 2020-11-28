"""Sensor platform for frigate."""
import logging
from .const import DEFAULT_NAME, DOMAIN, ICON, SENSOR, NAME, VERSION
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
        else:
            devices.extend([CameraFpsSensor(coordinator, entry, key, t) for t in CAMERA_FPS_TYPES])

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
