"""Frigate Media Source Implementation."""
import datetime as dt
import logging
import re
from typing import Optional, Tuple

from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_VIDEO,
    MEDIA_TYPE_CHANNEL,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source.const import MEDIA_MIME_TYPES
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FrigateApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
MIME_TYPE = "video/mp4"


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Frigate media source."""
    return FrigateSource(hass)


class FrigateSource(MediaSource):
    """Provide Frigate camera recordings as media sources."""

    name: str = "Frigate"

    def __init__(self, hass: HomeAssistant):
        """Initialize Frigate source."""
        super().__init__(DOMAIN)
        self.hass = hass
        session = async_get_clientsession(hass)
        host = self.hass.data[DOMAIN]["host"]
        self.client = FrigateApiClient(host, session)

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        return PlayMedia(f"/api/frigate/clips/{item.identifier}.mp4", MIME_TYPE)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: Tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Return media."""
        if item.identifier is None:
            events = await self.client.async_get_events()
        return self._browse_media(events)

    def _browse_media(
        self, events
    ) -> BrowseMediaSource:
        """Browse media."""

        return self._build_item_response(events)

    def _build_item_response(
        self, events
    ) -> BrowseMediaSource:
        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MEDIA_CLASS_DIRECTORY,
            children_media_class=MEDIA_CLASS_VIDEO,
            media_content_type=None,
            title="Frigate",
            can_play=False,
            can_expand=True,
            thumbnail=None
        )

        base.children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{event['camera']}-{event['id']}",
                media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=f"{event['label']}",
                can_play=True,
                can_expand=False,
                thumbnail=f"data:image/jpeg;base64,{event['thumbnail']}",
            )
            for event in events
        ]

        return base
