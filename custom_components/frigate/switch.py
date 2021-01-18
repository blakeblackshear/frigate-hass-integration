"""Sensor platform for frigate."""
import logging
from .const import (
    DEFAULT_NAME, DOMAIN, NAME, VERSION
)
from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.mqtt import async_publish
from homeassistant.components.mqtt.subscription import async_subscribe_topics

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup switch platform."""
    devices = []

    frigate_config = hass.data[DOMAIN]["config"]

    cameras = frigate_config["cameras"].keys()

    for cam in cameras:
        devices.extend([
            FrigateSwitch(hass, entry, frigate_config, cam, 'detect'),
            FrigateSwitch(hass, entry, frigate_config, cam, 'clips'),
            FrigateSwitch(hass, entry, frigate_config, cam, 'snapshots')
        ])

    async_add_devices(devices)


class FrigateSwitch(SwitchEntity):
    """Frigate Switch class."""

    def __init__(self, hass, entry, frigate_config, cam_name, switch_name):
        self.hass = hass
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._switch_name = switch_name
        self._state = False
        self._available = False
        self._sub_state = None
        self._state_topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._switch_name}/state"
        self._command_topic = f"{self._frigate_config['mqtt']['topic_prefix']}/{self._cam_name}/{self._switch_name}/set"
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
            self._state = msg.payload == 'ON'

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
                    "topic": self._state_topic,
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
        return f"{DOMAIN}_{self._cam_name}_{self._switch_name}_switch"

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
        return f"{friendly_camera_name} {self._switch_name}".title()

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def assumed_state(self):
        """Return true if we do optimistic updates."""
        return False

    async def async_turn_on(self, **kwargs):
        """Turn the device on.
        This method is a coroutine.
        """
        async_publish(
            self.hass,
            self._command_topic,
            'ON',
            0,
            True,
        )

    async def async_turn_off(self, **kwargs):
        """Turn the device off.
        This method is a coroutine.
        """
        async_publish(
            self.hass,
            self._command_topic,
            'OFF',
            0,
            True,
        )

    @property
    def icon(self):
        """Return the icon of the sensor."""
        if self._switch_name == "snapshots":
            return "mdi:image-multiple"
        if self._switch_name == "clips":
            return "mdi:filmstrip-box-multiple"
        return "hass:motion-sensor"

    @property
    def available(self) -> bool:
        return self._available
