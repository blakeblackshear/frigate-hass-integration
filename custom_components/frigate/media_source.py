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
from homeassistant.util.dt import DEFAULT_TIME_ZONE
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FrigateApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
MIME_TYPE = "video/mp4"
ITEM_LIMIT = 50
SECONDS_IN_DAY = 60 * 60 * 24
SECONDS_IN_MONTH = SECONDS_IN_DAY * 31


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

        identifier = None
        if item.identifier is None:
            # if the summary data is old, refresh
            if self.last_summary_refresh is None or dt.datetime.now().timestamp() - self.last_summary_refresh > 60:
                self.last_summary_refresh = dt.datetime.now().timestamp()
                self.summary_data = await self.client.async_get_event_summary()
                self.cameras = list(set([d["camera"] for d in self.summary_data]))
                self.labels = list(set([d["label"] for d in self.summary_data]))
                for d in self.summary_data:
                    d['timestamp'] = int(DEFAULT_TIME_ZONE.localize(dt.datetime.strptime(d['day'], '%Y-%m-%d')).timestamp())

            identifier = {
                "original": "",
                "name": "",
                "after": "",
                "before": "",
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
            limit=10000 if identifier['name'].endswith('.all') else ITEM_LIMIT
        )

        return self._browse_media(identifier, events)

    def _browse_media(
        self, identifier, events
    ) -> BrowseMediaSource:
        """Browse media."""

        after = int(identifier['after']) if not identifier['after'] == '' else None
        before = int(identifier['before']) if not identifier['before'] == '' else None
        count = self._count_by(after=after, before=before, camera=identifier['camera'], label=identifier['label'])

        if identifier["original"] == "":
            title = f"Frigate ({count})"
        else:
            title = f"{' > '.join([s for s in identifier['name'].replace('_', ' ').split('.') if s != '']).title()} ({count})"

        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MEDIA_CLASS_DIRECTORY,
            children_media_class=MEDIA_CLASS_VIDEO,
            media_content_type=None,
            title=title,
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=[]
        )

        event_items = self._build_item_response(events)

        drilldown_sources = []
        drilldown_sources.extend(self._build_date_sources(identifier))
        if identifier["camera"] == '':
            drilldown_sources.extend(self._build_camera_sources(identifier))
        if identifier["label"] == '':
            drilldown_sources.extend(self._build_label_sources(identifier))

        # if you are at the limit, but not at the root
        if len(event_items) == ITEM_LIMIT and not identifier["original"] == "":
            # only render if > 10% is represented in view
            if ITEM_LIMIT / float(count) > .1:
                base.children.extend(event_items)
        else:
            base.children.extend(event_items)

        # only show the drill down options if there are more than 10 events
        # and there is more than 1 drilldown or when you arent showing any events
        if len(events) > 10 and (len(drilldown_sources) > 1 or len(base.children) == 0):
            base.children.extend(drilldown_sources)

        # add an all source if there are no drilldowns available and you are at the item limit
        if len(drilldown_sources) == 0 and not identifier['name'].endswith('.all') and len(event_items) == ITEM_LIMIT:
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.all/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"All ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

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
        sources = []
        for c in self.cameras:
            after = int(identifier['after']) if not identifier['after'] == '' else None
            before = int(identifier['before']) if not identifier['before'] == '' else None
            count = self._count_by(after=after, before=before, camera=c, label=identifier['label'])
            if count == 0:
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.{c}/{identifier['after']}/{identifier['before']}/{c}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"{c.replace('_', ' ').title()} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )
        return sources

    def _build_label_sources(
        self, identifier
    ) -> BrowseMediaSource:
        sources = []
        for l in self.labels:
            after = int(identifier['after']) if not identifier['after'] == '' else None
            before = int(identifier['before']) if not identifier['before'] == '' else None
            count = self._count_by(after=after, before=before, camera=identifier['camera'], label=l)
            if count == 0:
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.{l}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{l}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"{l.replace('_', ' ').title()} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )
        return sources

    def _build_date_sources(
        self, identifier
    ) -> BrowseMediaSource:
        sources = []

        start_of_today = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(dt.datetime.today(), dt.time.min)).timestamp())
        start_of_yesterday = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(dt.datetime.today() - dt.timedelta(days=1), dt.time.min)).timestamp())
        start_of_month = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(dt.datetime.today().replace(day=1), dt.time.min)).timestamp())
        start_of_last_month = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(dt.datetime.today().replace(day=1) + relativedelta(months=+1), dt.time.min)).timestamp())
        start_of_year = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(dt.datetime.today().replace(month=1, day=1), dt.time.min)).timestamp())

        count_today = self._count_by(after=start_of_today, camera=identifier['camera'], label=identifier['label'])
        count_yesterday = self._count_by(after=start_of_yesterday, before=start_of_today, camera=identifier['camera'], label=identifier['label'])
        count_this_month = self._count_by(after=start_of_month, camera=identifier['camera'], label=identifier['label'])
        count_last_month = self._count_by(after=start_of_last_month, before=start_of_month, camera=identifier['camera'], label=identifier['label'])
        count_this_year = self._count_by(after=start_of_year, camera=identifier['camera'], label=identifier['label'])

        # if a date range has already been selected
        if identifier['before'] != '' or identifier['after'] != '':
            before = int(dt.datetime.now().timestamp()) if identifier['before'] == '' else int(identifier['before'])
            after = int(dt.datetime.now().timestamp()) if identifier['after'] == '' else int(identifier['after'])

            # if we are looking at years, split into months
            if before - after > SECONDS_IN_MONTH:
                current = after
                while (current < before):
                    current_date = dt.datetime.fromtimestamp(current)
                    start_of_current_month = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(current_date.date().replace(day=1), dt.time.min)).timestamp())
                    start_of_next_month = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(current_date.date().replace(day=1) + relativedelta(months=+1), dt.time.min)).timestamp())
                    count_current = self._count_by(after=start_of_current_month, before=start_of_next_month, camera=identifier['camera'], label=identifier['label'])
                    sources.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=f"{identifier['name']}.{current_date.strftime('%Y-%m')}/{start_of_current_month}/{start_of_next_month}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                            media_class=MEDIA_CLASS_DIRECTORY,
                            children_media_class=MEDIA_CLASS_VIDEO,
                            media_content_type=None,
                            title=f"{current_date.strftime('%B')} ({count_current})",
                            can_play=False,
                            can_expand=True,
                            thumbnail=None
                        )
                    )
                    current = current + SECONDS_IN_MONTH
                return sources

            # if we are looking at a month, split into days
            if before - after > SECONDS_IN_DAY:
                current = after
                while (current < before):
                    current_date = dt.datetime.fromtimestamp(current)
                    start_of_current_day = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(current_date.date(), dt.time.min)).timestamp())
                    start_of_next_day = int(DEFAULT_TIME_ZONE.localize(dt.datetime.combine(current_date.date() + dt.timedelta(days=1), dt.time.min)).timestamp())
                    count_current = self._count_by(after=start_of_current_day, before=start_of_next_day, camera=identifier['camera'], label=identifier['label'])
                    if count_current > 0:
                        sources.append(
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=f"{identifier['name']}.{current_date.strftime('%Y-%m-%d')}/{start_of_current_day}/{start_of_next_day}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                                media_class=MEDIA_CLASS_DIRECTORY,
                                children_media_class=MEDIA_CLASS_VIDEO,
                                media_content_type=None,
                                title=f"{current_date.strftime('%B %d')} ({count_current})",
                                can_play=False,
                                can_expand=True,
                                thumbnail=None
                            )
                        )
                    current = current + SECONDS_IN_DAY
                return sources

            return sources

        if count_today > 0:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.today/{start_of_today}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"Today ({count_today})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

        if count_yesterday > 0:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.yesterday/{start_of_yesterday}/{start_of_today}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"Yesterday ({count_yesterday})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

        if count_this_month > count_today + count_yesterday:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.this_month/{start_of_month}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"This Month ({count_this_month})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

        if count_last_month > 0:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.last_month/{start_of_last_month}/{start_of_month}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title=f"Last Month ({count_last_month})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

        if count_this_year > count_this_month + count_last_month:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['name']}.this_year/{start_of_year}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=None,
                    title="This Year",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None
                )
            )

        return sources

    def _count_by(self, after=None, before=None, camera='', label=''):
        return sum([d['count'] for d in self.summary_data if (
            (after is None or d['timestamp'] >= after) and
            (before is None or d['timestamp'] < before) and
            (camera == '' or d['camera'] == camera) and
            (label == '' or d['label'] == label)
        )])
