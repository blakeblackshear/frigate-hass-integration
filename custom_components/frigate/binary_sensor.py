"""Binary sensor platform for frigate."""
import logging
from .const import (
    DEFAULT_NAME, DOMAIN, PERSON_ICON, CAR_ICON, DOG_ICON, CAT_ICON,
    OTHER_ICON, SENSOR, NAME, VERSION
)
from homeassistant.core import callback
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.components.binary_sensor import DEVICE_CLASS_MOTION, BinarySensorEntity
from homeassistant.components.mqtt.subscription import async_subscribe_topics

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    frigate_config = hass.data[DOMAIN]["config"]

    camera_objects = [(cam_name, obj) for cam_name, cam_config in frigate_config["cameras"].items() for obj in cam_config["objects"]["track"]]

    zone_objects = []
    for cam, obj in camera_objects:
        for zone_name in frigate_config["cameras"][cam]["zones"]:
            zone_objects.append((zone_name, obj))
    zone_objects = list(set(zone_objects))

    async_add_devices([
        FrigateMotionSensor(hass, entry, frigate_config, cam_name, obj)
        for cam_name, obj in camera_objects + zone_objects
    ])


class FrigateMotionSensor(BinarySensorEntity):
    """Frigate Motion Sensor class."""

    def __init__(self, hass, entry, frigate_config, cam_name, obj_name):
        self.hass = hass
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._is_on = False
        self._available = False
        self._sub_state = None
        self._topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._obj_name}"
        self._availability_topic = f"{self._frigate_config['mqtt']['topic_prefix']}/available"

    async def async_added_to_hass(self):
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""
        @callback
        def state_message_received(msg):
            """Handle a new received MQTT state message."""
            payload = int(msg.payload)

            if payload > 0:
                self._is_on = True
            else:
                self._is_on = False

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
        return f"{DOMAIN}_{self._cam_name}_{self._obj_name}_binary_sensor"

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
        return f"{friendly_camera_name} {self._obj_name} Motion".title()

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def device_class(self):
        return DEVICE_CLASS_MOTION

    @property
    def available(self) -> bool:
        return self._available
