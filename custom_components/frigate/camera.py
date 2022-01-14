"""Support for Frigate cameras."""
from __future__ import annotations

import logging
from typing import Any, cast

import aiohttp
import async_timeout
from jinja2 import Template
from yarl import URL

from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FrigateEntity,
    FrigateMQTTEntity,
    ReceiveMessage,
    get_cameras_and_objects,
    get_friendly_name,
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from .const import (
    ATTR_CONFIG,
    CONF_RTMP_URL_TEMPLATE,
    DOMAIN,
    NAME,
    STATE_DETECTED,
    STATE_IDLE,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Camera entry setup."""

    config = hass.data[DOMAIN][entry.entry_id][ATTR_CONFIG]

    async_add_entities(
        [
            FrigateCamera(entry, cam_name, camera_config)
            for cam_name, camera_config in config["cameras"].items()
        ]
        + [
            FrigateMqttSnapshots(entry, config, cam_name, obj_name)
            for cam_name, obj_name in get_cameras_and_objects(config)
        ]
    )


class FrigateCamera(FrigateEntity, Camera):  # type: ignore[misc]
    """Representation a Frigate camera."""

    def __init__(
        self, config_entry: ConfigEntry, cam_name: str, camera_config: dict[str, Any]
    ) -> None:
        """Initialize a Frigate camera."""
        FrigateEntity.__init__(self, config_entry)
        Camera.__init__(self)
        self._cam_name = cam_name
        self._camera_config = camera_config
        self._url = config_entry.data[CONF_URL]
        self._attr_is_streaming = self._camera_config.get("rtmp", {}).get("enabled")
        self._attr_is_recording = self._camera_config.get("record", {}).get("enabled")

        streaming_template = config_entry.options.get(
            CONF_RTMP_URL_TEMPLATE, ""
        ).strip()

        if streaming_template:
            # Can't use homeassistant.helpers.template as it requires hass which
            # is not available in the constructor, so use direct jinja2
            # template instead. This means templates cannot access HomeAssistant
            # state, but rather only the camera config.
            self._stream_source = Template(streaming_template).render(
                **self._camera_config
            )
        else:
            self._stream_source = f"rtmp://{URL(self._url).host}/live/{self._cam_name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera",
            self._cam_name,
        )

    @property
    def name(self) -> str:
        """Return the name of the camera."""
        return get_friendly_name(self._cam_name)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device information."""
        return {
            "identifiers": {
                get_frigate_device_identifier(self._config_entry, self._cam_name)
            },
            "via_device": get_frigate_device_identifier(self._config_entry),
            "name": get_friendly_name(self._cam_name),
            "model": self._get_model(),
            "manufacturer": NAME,
        }

    @property
    def supported_features(self) -> int:
        """Return supported features of this camera."""
        if not self._attr_is_streaming:
            return 0
        return cast(int, SUPPORT_STREAM)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        websession = cast(aiohttp.ClientSession, async_get_clientsession(self.hass))

        image_url = str(
            URL(self._url)
            / f"api/{self._cam_name}/latest.jpg"
            % ({"h": height} if height is not None and height > 0 else {})
        )

        with async_timeout.timeout(10):
            response = await websession.get(image_url)
            return await response.read()

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        if not self._attr_is_streaming:
            return None
        return self._stream_source


class FrigateMqttSnapshots(FrigateMQTTEntity, Camera):  # type: ignore[misc]
    """Frigate best camera class."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        frigate_config: dict[str, Any],
        cam_name: str,
        obj_name: str,
    ) -> None:
        """Construct a FrigateMqttSnapshots camera."""
        self._cam_name = cam_name
        self._obj_name = obj_name
        self._last_image: bytes | None = None

        FrigateMQTTEntity.__init__(
            self,
            config_entry,
            frigate_config,
            {
                "topic": (
                    f"{frigate_config['mqtt']['topic_prefix']}"
                    f"/{self._cam_name}/{self._obj_name}/snapshot"
                ),
                "encoding": None,
            },
        )
        Camera.__init__(self)

    @callback  # type: ignore[misc]
    def _state_message_received(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT state message."""
        self._last_image = msg.payload
        super()._state_message_received(msg)

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return get_frigate_entity_unique_id(
            self._config_entry.entry_id,
            "camera_snapshots",
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
            "manufacturer": NAME,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{get_friendly_name(self._cam_name)} {self._obj_name}".title()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return image response."""
        return self._last_image

    @property
    def state(self) -> str:
        """Return the camera state."""
        if self._last_image is None:
            return STATE_IDLE
        return STATE_DETECTED
