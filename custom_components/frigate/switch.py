"""Sensor platform for frigate."""
import logging

from homeassistant.components.mqtt import async_publish
from homeassistant.components.mqtt.subscription import async_subscribe_topics
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_friendly_name, get_frigate_device_identifier
from .const import DOMAIN, NAME, VERSION

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Switch entry setup."""
    frigate_config = hass.data[DOMAIN]["config"]

    entities = []
    for camera in frigate_config["cameras"].keys():
        entities.extend(
            [
                FrigateSwitch(entry, frigate_config, camera, "detect"),
                FrigateSwitch(entry, frigate_config, camera, "clips"),
                FrigateSwitch(entry, frigate_config, camera, "snapshots"),
            ]
        )
    async_add_entities(entities)


class FrigateSwitch(SwitchEntity):
    """Frigate Switch class."""

    def __init__(self, entry, frigate_config, cam_name, switch_name):
        """Construct a FrigateSwitch."""
        self._entry = entry
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._switch_name = switch_name
        self._is_on = False
        self._available = False
        self._sub_state = None
        self._state_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/{self._switch_name}/state"
        )
        self._command_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}"
            f"/{self._cam_name}/{self._switch_name}/set"
        )
        self._availability_topic = (
            f"{self._frigate_config['mqtt']['topic_prefix']}/available"
        )

    async def async_added_to_hass(self):
        """Subscribe mqtt events."""
        await super().async_added_to_hass()
        await self._subscribe_topics()

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""

        @callback
        def state_message_received(msg):
            """Handle a new received MQTT state message."""
            self._is_on = msg.payload == "ON"
            self.async_write_ha_state()

        @callback
        def availability_message_received(msg: str) -> None:
            """Handle a new received MQTT availability message."""
            self._available = msg.payload == "online"
            self.async_write_ha_state()

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
                },
            },
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._cam_name}_{self._switch_name}_switch"

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
        return f"{get_friendly_name(self._cam_name)} {self._switch_name}".title()

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        async_publish(
            self.hass,
            self._command_topic,
            "ON",
            0,
            True,
        )

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        async_publish(
            self.hass,
            self._command_topic,
            "OFF",
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
        """Determine if the entity is available."""
        return self._available
