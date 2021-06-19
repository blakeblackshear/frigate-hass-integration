"""Frigate Media Source."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from dateutil.relativedelta import relativedelta

from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_VIDEO,
)
from homeassistant.components.media_source.const import MEDIA_MIME_TYPES
from homeassistant.components.media_source.error import MediaSourceError
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.template import DATE_STR_FORMAT
from homeassistant.util.dt import DEFAULT_TIME_ZONE

from . import get_friendly_name
from .api import FrigateApiClient, FrigateApiClientError
from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)
MIME_TYPE = "video/mp4"
ITEM_LIMIT = 50
SECONDS_IN_DAY = 60 * 60 * 24
SECONDS_IN_MONTH = SECONDS_IN_DAY * 31
CLIPS_ROOT = "clips//////"
RECORDINGS_ROOT = "recordings////"


async def async_get_media_source(hass: HomeAssistant):
    """Set up Frigate media source."""
    return FrigateMediaSource(hass)


class FrigateMediaSource(MediaSource):
    """Provide Frigate camera recordings as media sources."""

    name: str = "Frigate"

    def __init__(self, hass: HomeAssistant):
        """Initialize Frigate source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self._client = FrigateApiClient(
            self.hass.data[DOMAIN]["host"], async_get_clientsession(hass)
        )
        self._last_summary_refresh = None
        self._summary_data = None
        self._cameras = []
        self._labels = []
        self._zones = []

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        return PlayMedia(f"/api/frigate/{item.identifier}", MIME_TYPE)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Browse media."""

        if item.identifier is None:
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier="",
                media_class=MEDIA_CLASS_DIRECTORY,
                children_media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_CLASS_VIDEO,
                title=NAME,
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

        if item.identifier.startswith("clips"):
            identifier = None

            # If the summary data is old, refresh it.
            if (
                self._last_summary_refresh is None
                or dt.datetime.now().timestamp() - self._last_summary_refresh > 60
            ):
                self._last_summary_refresh = dt.datetime.now().timestamp()
                try:
                    self._summary_data = await self._client.async_get_event_summary()
                except FrigateApiClientError as exc:
                    raise MediaSourceError from exc

                self._cameras = list({d["camera"] for d in self._summary_data})
                self._labels = list({d["label"] for d in self._summary_data})
                self._zones = list(
                    {zone for d in self._summary_data for zone in d["zones"]}
                )
                for data in self._summary_data:
                    data["timestamp"] = int(
                        dt.datetime.strptime(data["day"], "%Y-%m-%d")
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

            try:
                events = await self._client.async_get_events(
                    after=identifier["after"],
                    before=identifier["before"],
                    camera=identifier["camera"],
                    label=identifier["label"],
                    zone=identifier["zone"],
                    limit=10000 if identifier["name"].endswith(".all") else ITEM_LIMIT,
                )
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc

            return self._browse_clips(identifier, events)

        if item.identifier.startswith("recordings"):
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
                try:
                    folders = await self._client.async_get_recordings_folder(path)
                except FrigateApiClientError as exc:
                    raise MediaSourceError from exc
                return self._browse_recording_folders(identifier, folders)

            path = "/".join([s for s in item.identifier.split("/")[1:] if s != ""])
            try:
                recordings = await self._client.async_get_recordings_folder(path)
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc
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
            title = f"{' > '.join([s for s in get_friendly_name(identifier['name']).split('.') if s != '']).title()} ({count})"

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
        if (
            count > 0
            and len(event_items) == ITEM_LIMIT
            and not identifier["original"] == CLIPS_ROOT
        ):
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
        # and there is more than 1 drilldown or when you aren't showing any events
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

    @classmethod
    def _build_clip_response(cls, events) -> BrowseMediaSource:
        return [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"clips/{event['camera']}-{event['id']}.mp4",
                media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=f"{dt.datetime.fromtimestamp(event['start_time'], DEFAULT_TIME_ZONE).strftime(DATE_STR_FORMAT)} [{int(event['end_time']-event['start_time'])}s, {event['label'].capitalize()} {int(event['top_score']*100)}%]",
                can_play=True,
                can_expand=False,
                thumbnail=f"data:image/jpeg;base64,{event['thumbnail']}",
            )
            for event in events
        ]

    def _build_camera_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for camera in self._cameras:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=camera,
                label=identifier["label"],
                zone=identifier["zone"],
            )
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{camera}/{identifier['after']}/{identifier['before']}/{camera}/{identifier['label']}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{get_friendly_name(camera)} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return sources

    def _build_label_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for label in self._labels:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=identifier["camera"],
                label=label,
                zone=identifier["zone"],
            )
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{label}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{label}/{identifier['zone']}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{get_friendly_name(label)} ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return sources

    def _build_zone_sources(self, identifier, shown_event_count) -> BrowseMediaSource:
        sources = []
        for zone in self._zones:
            after = int(identifier["after"]) if not identifier["after"] == "" else None
            before = (
                int(identifier["before"]) if not identifier["before"] == "" else None
            )
            count = self._count_by(
                after=after,
                before=before,
                camera=identifier["camera"],
                label=identifier["label"],
                zone=zone,
            )
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"clips/{identifier['name']}.{zone}/{identifier['after']}/{identifier['before']}/{identifier['camera']}/{identifier['label']}/{zone}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=f"{get_friendly_name(zone)} ({count})",
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
                for d in self._summary_data
                if (
                    (after is None or d["timestamp"] >= after)
                    and (before is None or d["timestamp"] < before)
                    and (camera == "" or camera in d["camera"])
                    and (label == "" or label in d["label"])
                    and (zone == "" or zone in d["zones"])
                )
            ]
        )

    @classmethod
    def _create_recordings_folder_identifier(cls, identifier, folder):
        identifier_fragments = [
            s for s in identifier["original"].split("/") if s != ""
        ] + [folder["name"]]
        identifier_fragments += [""] * (5 - len(identifier_fragments))
        return "/".join(identifier_fragments)

    @classmethod
    def _generate_recording_title(
        cls, identifier: dict[str, Any], folder: str = None
    ) -> str | None:
        """Generate recording title."""
        try:
            if identifier["camera"] != "":
                if folder is None:
                    return get_friendly_name(identifier["camera"])
                minute_seconds = folder["name"].replace(".mp4", "")
                return dt.datetime.strptime(
                    f"{identifier['hour']}.{minute_seconds}", "%H.%M.%S"
                ).strftime("%T")

            if identifier["hour"] != "":
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier['hour']}.00.00", "%H.%M.%S"
                    ).strftime("%T")
                return get_friendly_name(folder["name"])

            if identifier["day"] != "":
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier['year_month']}-{identifier['day']}", "%Y-%m-%d"
                    ).strftime("%B %d")
                return dt.datetime.strptime(
                    f"{folder['name']}.00.00", "%H.%M.%S"
                ).strftime("%T")

            if identifier["year_month"] != "":
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier['year_month']}", "%Y-%m"
                    ).strftime("%B %Y")
                return dt.datetime.strptime(
                    f"{identifier['year_month']}-{folder['name']}", "%Y-%m-%d"
                ).strftime("%B %d")

            if folder is None:
                return [s for s in identifier["original"].split("/") if s != ""][
                    -1
                ].title()
            return dt.datetime.strptime(f"{folder['name']}", "%Y-%m").strftime("%B %Y")
        except ValueError:
            return None

    def _get_recording_base_media_source(
        self, identifier: dict[str, Any]
    ) -> BrowseMediaSource:
        """Get the base BrowseMediaSource object for a recording identifier."""
        title = self._generate_recording_title(identifier)

        # Must be able to generate a title for the source folder.
        if not title:
            raise MediaSourceError

        return BrowseMediaSource(
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

    def _browse_recording_folders(
        self, identifier: dict[str, Any], folders: dict[str, Any]
    ) -> BrowseMediaSource:
        """Browse Frigate recording folders."""
        base = self._get_recording_base_media_source(identifier)

        for folder in folders:
            if folder["name"].endswith(".mp4"):
                continue
            title = self._generate_recording_title(identifier, folder)
            if not title:
                _LOGGER.warning("Skipping non-standard folder name: %s", folder["name"])
                continue
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=self._create_recordings_folder_identifier(
                        identifier, folder
                    ),
                    media_class=MEDIA_CLASS_DIRECTORY,
                    children_media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_CLASS_VIDEO,
                    title=title,
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        return base

    def _browse_recordings(
        self, identifier: dict[str, Any], recordings: dict[str, Any]
    ) -> BrowseMediaSource:
        """Browse Frigate recordings."""
        base = self._get_recording_base_media_source(identifier)

        for recording in recordings:
            title = self._generate_recording_title(identifier, recording)
            if not title:
                _LOGGER.warning(
                    "Skipping non-standard recording name: %s", recording["name"]
                )
                continue
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{identifier['original']}/{recording['name']}",
                    media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_TYPE_VIDEO,
                    title=title,
                    can_play=True,
                    can_expand=False,
                    thumbnail=None,
                )
            )
        return base
