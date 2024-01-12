"""Support for Frigate images."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import ATTR_CONFIG, DOMAIN, NAME

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Image entry setup."""

    frigate_config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    async_add_entities(
        [
            FrigateMqttSnapshots(hass, entry, frigate_config, cam_name, obj_name)
            for cam_name, obj_name in get_cameras_and_objects(frigate_config, False)
        ]
    )


class FrigateMqttSnapshots(FrigateMQTTEntity, ImageEntity):  # type: ignore[misc]
    """Frigate best image class."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateMqttSnapshots image."""
        self._frigate_config = frigate_config
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._last_image_timestamp: datetime.datetime | None = None
        self._last_image: bytes | None = None

        FrigateMQTTEntity.__init__(
            self,
            config_entry,
            frigate_config,
            {
                "state_topic": {
                    "msg_callback": self._state_message_received,
                    "qos": 0,
                    "topic": (
                        f"{self._frigate_config['mqtt']['topic_prefix']}"
                        f"/{self._cam_name}/{self._obj_name}/snapshot"
                    ),
                    "encoding": None,
                },
            },
        )
        ImageEntity.__init__(self, hass)

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._last_image_timestamp = datetime.datetime.now()
        self._last_image = msg.payload
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "image_best_snapshot",
            f"{self._cam_name}_{self._obj_name}",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Get the device information."""
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
        return self._obj_name.title()

    @property
    def image_last_updated(self) -> datetime.datetime | None:
        """Return timestamp of last image update."""
        return self._last_image_timestamp

    def image(
        self,
    ) -> bytes | None:  # pragma: no cover (HA currently does not support a direct way to test this)
        """Return bytes of image."""
        return self._last_image
