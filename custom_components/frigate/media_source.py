"""Frigate Media Source Implementation."""
import datetime as dt
from dateutil.relativedelta import *
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
        self.last_summary_refresh = None
        self.summary_data = None

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        return PlayMedia(f"/api/frigate/clips/{item.identifier}.mp4", MIME_TYPE)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: Tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Return media."""

        _LOGGER.info(f"Browsing identifier: {item.identifier}")

        identifier = None
        if item.identifier is None:
            # if the summary data is old, refresh
            if self.last_summary_refresh is None or dt.datetime.now().timestamp() - self.last_summary_refresh > 60:
                self.last_summary_refresh = dt.datetime.now().timestamp()
                self.summary_data = await self.client.async_get_event_summary()
                self.cameras = list(set([d["camera"] for d in self.summary_data]))
                self.labels = list(set([d["label"] for d in self.summary_data]))

            identifier = {
                "original": "",
                "name": "",
                "after": None,
                "before": None,
                "camera": "",
                "label": "",
                "zone": ""
            }
        else:
            identifier_parts = item.identifier.split("/")
            identifier = {
                "original": item.identifier,
                "name": identifier_parts[0],
                "after": identifier_parts[1],
                "before": identifier_parts[2],
                "camera": identifier_parts[3],
                "label": identifier_parts[4],
                "zone": identifier_parts[5]
            }

        events = await self.client.async_get_events(
            after=identifier["after"],
            before=identifier["before"],
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
            limit=25
        )

        return self._browse_media(identifier, events)

    def _browse_media(
        self, identifier, events
    ) -> BrowseMediaSource:
        """Browse media."""

        if identifier["original"] == "":
            base = BrowseMediaSource(
                domain=DOMAIN,
                identifier="",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="Frigate",
                can_play=False,
                can_expand=True,
                thumbnail=None,
                children=self._build_item_response(events),
            )
            base.children.extend(self._build_date_sources(identifier))
        else:
            base = BrowseMediaSource(
                domain=DOMAIN,
                identifier=identifier["original"],
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title=identifier["name"].replace("_", " ").title(),
                can_play=False,
                can_expand=True,
                thumbnail=None,
                children=self._build_item_response(events)
            )
            if identifier["camera"] == '':
                base.children.extend(self._build_camera_sources(identifier))
            if identifier["label"] == '':
                base.children.extend(self._build_label_sources(identifier))
        return base

    def _build_item_response(
        self, events
    ) -> BrowseMediaSource:
        return [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{event['camera']}-{event['id']}",
                media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=f"{event['label']} {int(event['top_score']*100)}%".capitalize(),
                can_play=True,
                can_expand=False,
                thumbnail=f"data:image/jpeg;base64,{event['thumbnail']}",
            )
            for event in events
        ]

    def _build_camera_sources(
        self, identifier
    ) -> BrowseMediaSource:
        return [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{identifier['name']} > {c}/{identifier['after']}/{identifier['before']}/{c}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title=c.replace("_", " ").title(),
                can_play=False,
                can_expand=True,
                thumbnail=None
            )
            for c in self.cameras
        ]

    def _build_label_sources(
        self, identifier
    ) -> BrowseMediaSource:
        return [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{identifier['name']} > {l}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{l}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title=l.replace("_", " ").title(),
                can_play=False,
                can_expand=True,
                thumbnail=None
            )
            for l in self.labels
        ]

    def _build_date_sources(
        self, identifier
    ) -> BrowseMediaSource:
        start_of_today = int(dt.datetime.combine(dt.datetime.today(), dt.time.min).timestamp())
        start_of_yesterday = int(dt.datetime.combine(dt.datetime.today() - dt.timedelta(days=1), dt.time.min).timestamp())
        start_of_month = int(dt.datetime.combine(dt.datetime.today().replace(day=1), dt.time.min).timestamp())
        start_of_last_month = int(dt.datetime.combine(dt.datetime.today().replace(day=1) + relativedelta(months=+1), dt.time.min).timestamp())
        start_of_year = int(dt.datetime.combine(dt.datetime.today().replace(month=1, day=1), dt.time.min).timestamp())
        sources = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"today/{start_of_today}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="Today",
                can_play=False,
                can_expand=True,
                thumbnail=None
            ),
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"yesterday/{start_of_yesterday}/{start_of_today}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="Yesterday",
                can_play=False,
                can_expand=True,
                thumbnail=None
            ),
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"this_month/{start_of_month}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="This Month",
                can_play=False,
                can_expand=True,
                thumbnail=None
            ),
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"last_month/{start_of_last_month}/{start_of_month}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="Last Month",
                can_play=False,
                can_expand=True,
                thumbnail=None
            ),
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"this_year/{start_of_year}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=None,
                title="This Year",
                can_play=False,
                can_expand=True,
                thumbnail=None
            )
        ]
        # determine which of the following make sense based on the current identifier
        # and the summary data
        # today, yesterday, this month, last month, this year, last year

        # determine the number of events within each of the above buckets, filtered by (camera, label)

        # if num of events for current identifier 25 or less, no further drill down needed (probably do this in parent function)

        # if num of events

        return sources

    def _count_by(self, group: str, after: int, before: int, camera=None, label=None):
        # group should be day, week, month, or year
        events_today = sum([d['count'] for d in self.summary_data if d['day'] == dt.datetime.now().strftime('%Y-%m-%d')])
        return {}
