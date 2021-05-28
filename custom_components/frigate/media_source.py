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
CLIPS_ROOT = "clips//////"
RECORDINGS_ROOT = "recordings////"


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
        return PlayMedia(f"/api/frigate/{item.identifier}", MIME_TYPE)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: Tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Return media."""

        if item.identifier is None:
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier="",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_CLASS_VIDEO,
                title="Frigate",
                can_play=False,
                can_expand=True,
                thumbnail=None,
                children=[
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=CLIPS_ROOT,
                        media_class=MEDIA_CLASS_DIRECTORY,
                        children_media_class=MEDIA_CLASS_VIDEO,
                        media_content_type=MEDIA_CLASS_VIDEO,
                        title="Clips",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                        children=[],
                    ),
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=RECORDINGS_ROOT,
                        media_class=MEDIA_CLASS_DIRECTORY,
                        children_media_class=MEDIA_CLASS_VIDEO,
                        media_content_type=MEDIA_CLASS_VIDEO,
                        title="Recordings",
                        can_play=False,
                        can_expand=True,
                        thumbnail=None,
                        children=[],
                    ),
                ],
            )

        elif item.identifier.startswith("clips"):
            identifier = None
            _LOGGER.debug(f"item.identifier: {item.identifier}")
            if item.identifier == CLIPS_ROOT:
                # if the summary data is old, refresh
                if (
                    self.last_summary_refresh is None
                    or dt.datetime.now().timestamp() - self.last_summary_refresh > 60
                ):
                    _LOGGER.debug(f"refreshing summary data")
                    self.last_summary_refresh = dt.datetime.now().timestamp()
                    self.summary_data = await self.client.async_get_event_summary()
                    self.cameras = list(set([d["camera"] for d in self.summary_data]))
                    self.labels = list(set([d["label"] for d in self.summary_data]))
                    self.zones = list(
                        set([zone for d in self.summary_data for zone in d["zones"]])
                    )
                    for d in self.summary_data:
                        d["timestamp"] = int(
                            dt.datetime.strptime(d["day"], "%Y-%m-%d")
                            .astimezone(DEFAULT_TIME_ZONE)
                            .timestamp()
                        )

            identifier_parts = item.identifier.split("/")
            identifier = {
                "original": item.identifier,
                "name": identifier_parts[1],
                "after": identifier_parts[2],
                "before": identifier_parts[3],
                "camera": identifier_parts[4],
                "label": identifier_parts[5],
                "zone": identifier_parts[6],
            }

            events = await self.client.async_get_events(
                after=identifier["after"],
                before=identifier["before"],
                camera=identifier["camera"],
                label=identifier["label"],
                zone=identifier["zone"],
                limit=10000 if identifier["name"].endswith(".all") else ITEM_LIMIT,
            )

            return self._browse_clips(identifier, events)

        elif item.identifier.startswith("recordings"):
            identifier_parts = item.identifier.split("/")
            identifier = {
                "original": item.identifier,
                "year_month": identifier_parts[1],
                "day": identifier_parts[2],
                "hour": identifier_parts[3],
                "camera": identifier_parts[4],
            }

            if identifier["camera"] == "":
                path = "/".join([s for s in item.identifier.split("/")[1:] if s != ""])
                folders = await self.client.async_get_recordings_folder(path)
                return self._browse_recording_folders(identifier, folders)

            path = "/".join([s for s in item.identifier.split("/")[1:] if s != ""])
            recordings = await self.client.async_get_recordings_folder(path)
            return self._browse_recordings(identifier, recordings)

    def _browse_clips(self, identifier, events) -> BrowseMediaSource:
        """Browse media."""

        after = int(identifier["after"]) if not identifier["after"] == "" else None
        before = int(identifier["before"]) if not identifier["before"] == "" else None
        count = self._count_by(
            after=after,
            before=before,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )

        if identifier["original"] == CLIPS_ROOT:
            title = f"Clips ({count})"
        else:
            title = f"{' > '.join([s for s in identifier['name'].replace('_', ' ').split('.') if s != '']).title()} ({count})"

        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier["original"],
            media_class=MEDIA_CLASS_DIRECTORY,
            children_media_class=MEDIA_CLASS_VIDEO,
            media_content_type=MEDIA_CLASS_VIDEO,
            title=title,
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=[],
        )

        event_items = self._build_clip_response(events)

        # if you are at the limit, but not at the root
        if len(event_items) == ITEM_LIMIT and not identifier["original"] == CLIPS_ROOT:
            # only render if > 10% is represented in view
            if ITEM_LIMIT / float(count) > 0.1:
                base.children.extend(event_items)
        else:
            base.children.extend(event_items)

        drilldown_sources = []
        drilldown_sources.extend(
            self._build_date_sources(identifier, len(base.children))
        )
        if identifier["camera"] == "":
            drilldown_sources.extend(
                self._build_camera_sources(identifier, len(base.children))
            )
        if identifier["label"] == "":
            drilldown_sources.extend(
                self._build_label_sources(identifier, len(base.children))
            )
        if identifier["zone"] == "":
            drilldown_sources.extend(
                self._build_zone_sources(identifier, len(base.children))
            )

        # only show the drill down options if there are more than 10 events
        # and there is more than 1 drilldown or when you arent showing any events
        if len(events) > 10 and (len(drilldown_sources) > 1 or len(base.children) == 0):
            base.children.extend(drilldown_sources)

        # add an all source if there are no drilldowns available and you are at the item limit
        if (
            (len(base.children) == 0 or len(base.children) == len(event_items))
            and not identifier["name"].endswith(".all")
            and len(event_items) == ITEM_LIMIT
        ):
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.all/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"All ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return base

    def _build_clip_response(self, events) -> BrowseMediaSource:
        return [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"clips/{event['camera']}-{event['id']}.mp4",
                media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=f"{dt.datetime.fromtimestamp(event['start_time'], DEFAULT_TIME_ZONE).strftime('%x %I:%M %p')} {event['label'].capitalize()} {int(event['top_score']*100)}% | {int(event['end_time']-event['start_time'])}s",
                can_play=True,
                can_expand=False,
                thumbnail=f"data:image/jpeg;base64,{event['thumbnail']}",
            )
            for event in events
        ]

    def _build_camera_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for c in self.cameras:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=c,
                label=identifier["label"],
                zone=identifier["zone"],
            )
            if count == 0 or count == shown_event_count:
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{c}/{identifier['after']}/{identifier['before']}/{c}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{c.replace('_', ' ').title()} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return sources

    def _build_label_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for l in self.labels:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=identifier["camera"],
                label=l,
                zone=identifier["zone"],
            )
            if count == 0 or count == shown_event_count:
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{l}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{l}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{l.replace('_', ' ').title()} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return sources

    def _build_zone_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for z in self.zones:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=identifier["camera"],
                label=identifier["label"],
                zone=z,
            )
            if count == 0 or count == shown_event_count:
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{z}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{identifier['label']}/{z}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{z.replace('_', ' ').title()} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return sources

    def _build_date_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []

        now = dt.datetime.now(DEFAULT_TIME_ZONE)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        start_of_today = int(today.timestamp())
        start_of_yesterday = start_of_today - SECONDS_IN_DAY
        start_of_month = int(today.replace(day=1).timestamp())
        start_of_last_month = int(
            (today.replace(day=1) + relativedelta(months=-1)).timestamp()
        )
        start_of_year = int(today.replace(month=1, day=1).timestamp())

        count_today = self._count_by(
            after=start_of_today,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )
        count_yesterday = self._count_by(
            after=start_of_yesterday,
            before=start_of_today,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )
        count_this_month = self._count_by(
            after=start_of_month,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )
        count_last_month = self._count_by(
            after=start_of_last_month,
            before=start_of_month,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )
        count_this_year = self._count_by(
            after=start_of_year,
            camera=identifier["camera"],
            label=identifier["label"],
            zone=identifier["zone"],
        )

        # if a date range has already been selected
        if identifier["before"] != "" or identifier["after"] != "":
            before = (
                int(now.timestamp())
                if identifier["before"] == ""
                else int(identifier["before"])
            )
            after = (
                int(now.timestamp())
                if identifier["after"] == ""
                else int(identifier["after"])
            )

            # if we are looking at years, split into months
            if before - after > SECONDS_IN_MONTH:
                current = after
                while current < before:
                    current_date = (
                        dt.datetime.fromtimestamp(current)
                        .astimezone(DEFAULT_TIME_ZONE)
                        .replace(hour=0, minute=0, second=0, microsecond=0)
                    )
                    start_of_current_month = int(current_date.timestamp())
                    start_of_next_month = int(
                        (current_date + relativedelta(months=+1)).timestamp()
                    )
                    count_current = self._count_by(
                        after=start_of_current_month,
                        before=start_of_next_month,
                        camera=identifier["camera"],
                        label=identifier["label"],
                        zone=identifier["zone"],
                    )
                    sources.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=f"clips/{identifier['name']}.{current_date.strftime('%Y-%m')}/{start_of_current_month}/{start_of_next_month}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                            media_class=MEDIA_CLASS_DIRECTORY,
                            children_media_class=MEDIA_CLASS_VIDEO,
                            media_content_type=MEDIA_CLASS_VIDEO,
                            title=f"{current_date.strftime('%B')} ({count_current})",
                            can_play=False,
                            can_expand=True,
                            thumbnail=None,
                        )
                    )
                    current = current + SECONDS_IN_MONTH
                return sources

            # if we are looking at a month, split into days
            if before - after > SECONDS_IN_DAY:
                current = after
                while current < before:
                    current_date = (
                        dt.datetime.fromtimestamp(current)
                        .astimezone(DEFAULT_TIME_ZONE)
                        .replace(hour=0, minute=0, second=0, microsecond=0)
                    )
                    start_of_current_day = int(current_date.timestamp())
                    start_of_next_day = start_of_current_day + SECONDS_IN_DAY
                    count_current = self._count_by(
                        after=start_of_current_day,
                        before=start_of_next_day,
                        camera=identifier["camera"],
                        label=identifier["label"],
                        zone=identifier["zone"],
                    )
                    if count_current > 0:
                        sources.append(
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=f"clips/{identifier['name']}.{current_date.strftime('%Y-%m-%d')}/{start_of_current_day}/{start_of_next_day}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                                media_class=MEDIA_CLASS_DIRECTORY,
                                children_media_class=MEDIA_CLASS_VIDEO,
                                media_content_type=MEDIA_CLASS_VIDEO,
                                title=f"{current_date.strftime('%B %d')} ({count_current})",
                                can_play=False,
                                can_expand=True,
                                thumbnail=None,
                            )
                        )
                    current = current + SECONDS_IN_DAY
                return sources

            return sources

        if count_today > shown_event_count:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.today/{start_of_today}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"Today ({count_today})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        if count_yesterday > shown_event_count:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.yesterday/{start_of_yesterday}/{start_of_today}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"Yesterday ({count_yesterday})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        if (
            count_this_month > count_today + count_yesterday
            and count_this_month > shown_event_count
        ):
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.this_month/{start_of_month}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"This Month ({count_this_month})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        if count_last_month > shown_event_count:
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.last_month/{start_of_last_month}/{start_of_month}/{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"Last Month ({count_last_month})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        if (
            count_this_year > count_this_month + count_last_month
            and count_this_year > shown_event_count
        ):
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.this_year/{start_of_year}//{identifier['camera']}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title="This Year",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return sources

    def _count_by(self, after=None, before=None, camera="", label="", zone=""):
        return sum(
            [
                d["count"]
                for d in self.summary_data
                if (
                    (after is None or d["timestamp"] >= after)
                    and (before is None or d["timestamp"] < before)
                    and (camera == "" or d["camera"] == camera)
                    and (label == "" or d["label"] == label)
                    and (zone == "" or zone in d["zones"])
                )
            ]
        )

    def _create_recordings_folder_identifier(self, identifier, folder):
        identifier_fragments = [
            s for s in identifier["original"].split("/") if s != ""
        ] + [folder["name"]]
        identifier_fragments += [""] * (5 - len(identifier_fragments))
        return "/".join(identifier_fragments)

    def _generate_recording_title(self, identifier, folder=None):
        if identifier["camera"] != "":
            if folder is None:
                return identifier["camera"].replace("_", " ").title()
            else:
                minute_seconds = folder["name"].replace(".mp4", "")
                return dt.datetime.strptime(
                    f"{identifier['hour']}.{minute_seconds}", "%H.%M.%S"
                ).strftime("%-I:%M:%S %p")

        if identifier["hour"] != "":
            if folder is None:
                return dt.datetime.strptime(
                    f"{identifier['hour']}.00.00", "%H.%M.%S"
                ).strftime("%-I:%M:%S %p")
            else:
                return folder["name"].replace("_", " ").title()

        if identifier["day"] != "":
            if folder is None:
                return dt.datetime.strptime(
                    f"{identifier['year_month']}-{identifier['day']}", "%Y-%m-%d"
                ).strftime("%B %d")
            else:
                return dt.datetime.strptime(
                    f"{folder['name']}.00.00", "%H.%M.%S"
                ).strftime("%-I:%M:%S %p")

        if identifier["year_month"] != "":
            if folder is None:
                return dt.datetime.strptime(
                    f"{identifier['year_month']}", "%Y-%m"
                ).strftime("%B %Y")
            else:
                return dt.datetime.strptime(
                    f"{identifier['year_month']}-{folder['name']}", "%Y-%m-%d"
                ).strftime("%B %d")

        if folder is None:
            return [s for s in identifier["original"].split("/") if s != ""][-1].title()
        else:
            return dt.datetime.strptime(f"{folder['name']}", "%Y-%m").strftime("%B %Y")

    def _browse_recording_folders(self, identifier, folders):
        children = []
        for folder in folders:
            if folder["name"].endswith(".mp4"):
                continue
            try:
                child = BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=self._create_recordings_folder_identifier(
                        identifier, folder
                    ),
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=self._generate_recording_title(identifier, folder),
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
                children.append(child)
            except:
                _LOGGER.warn(f"Skipping non-standard folder {folder['name']}")

        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier["original"],
            media_class=MEDIA_CLASS_DIRECTORY,
            children_media_class=MEDIA_CLASS_VIDEO,
            media_content_type=MEDIA_CLASS_VIDEO,
            title=self._generate_recording_title(identifier),
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=children,
        )

        return base

    def _browse_recordings(self, identifier, recordings):
        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier["original"],
            media_class=MEDIA_CLASS_DIRECTORY,
            children_media_class=MEDIA_CLASS_VIDEO,
            media_content_type=MEDIA_CLASS_VIDEO,
            title=self._generate_recording_title(identifier),
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['original']}/{recording['name']}",
                    media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_TYPE_VIDEO,
                    title=self._generate_recording_title(identifier, recording),
                    can_play=True,
                    can_expand=False,
                    thumbnail=None,
                )
                for recording in recordings
            ],
        )

        return base
