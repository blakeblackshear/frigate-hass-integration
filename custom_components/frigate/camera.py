"""Support for Frigate cameras."""
import async_timeout
from typing import Dict
import urllib.parse
import logging

from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.aiohttp_client import (
    async_aiohttp_proxy_web,
    async_get_clientsession,
)

from .const import (
    DOMAIN, NAME, VERSION
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistantType, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Synology NAS binary sensor."""

    config = hass.data[DOMAIN]["config"]

    entities = [FrigateCamera(hass, entry, name, camera) for name, camera in config['cameras'].items()]

    async_add_entities(entities)


class FrigateCamera(Camera):
    """Representation a Frigate camera."""

    def __init__(self, hass, config_entry, name: str, config: Dict):
        """Initialize a Frigate camera."""
        super().__init__()
        self.hass = hass
        self.config_entry = config_entry
        self._host = self.hass.data[DOMAIN]["host"]
        self._name = name
        _LOGGER.debug(f"Adding camera {name}")
        self._config = config
        self._latest_url = urllib.parse.urljoin(self._host, f"/{self._name}/latest.jpg")
        parsed_host = urllib.parse.urlparse(self._host).hostname
        self._stream_source = f"rtmp://{parsed_host}/live/{self._name}"

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._name}_camera"

    @property
    def name(self):
        """Return the name of the camera."""
        return f"{self._name.replace('_', ' ')}".title()

    @property
    def device_info(self) -> Dict[str, any]:
        """Return the device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def available(self) -> bool:
        """Return the availability of the camera."""
        return True

    @property
    def supported_features(self) -> int:
        """Return supported features of this camera."""
        return SUPPORT_STREAM

    # @ property
    # def is_recording(self):
    #     """Return true if the device is recording."""
    #     return False

    # @ property
    # def motion_detection_enabled(self):
    #     """Return the camera motion detection status."""
    #     return True

    async def async_camera_image(self) -> bytes:
        """Return bytes of camera image."""
        websession = async_get_clientsession(self.hass)

        with async_timeout.timeout(10):
            response = await websession.get(self._latest_url)

            image = await response.read()
            return image

    async def stream_source(self) -> str:
        """Return the source of the stream."""
        if not self.available:
            return None
        return self._stream_source
