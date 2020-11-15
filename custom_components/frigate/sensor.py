"""Sensor platform for frigate."""
from .const import DEFAULT_NAME, DOMAIN, ICON, SENSOR
from .entity import FrigateEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices([FrigateSensor(coordinator, entry)])


class FrigateSensor(FrigateEntity):
    """Frigate Sensor class."""

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{DEFAULT_NAME}_{SENSOR}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get("detection_fps")

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return ICON
