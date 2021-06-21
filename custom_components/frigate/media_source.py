"""Frigate Media Source."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import attr
from dateutil.relativedelta import relativedelta

from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_VIDEO,
)
from homeassistant.components.media_source.const import MEDIA_MIME_TYPES
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
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


async def async_get_media_source(hass: HomeAssistant):
    """Set up Frigate media source."""
    return FrigateMediaSource(hass)


class Identifier:
    """Base class for Identifiers."""

    @classmethod
    def _get_index(cls, data: list, index: int, default: Any = None) -> Any:
        try:
            return data[index] if data[index] != "" else default
        except IndexError:
            return default

    @classmethod
    def _empty_if_none(cls, data: Any) -> str:
        """Return an empty string if data is None."""
        return str(data) if data is not None else ""

    @classmethod
    def _to_int_or_none(cls, data: str) -> int | None:
        return int(data) if data else None

    @classmethod
    def from_str(
        cls, data: str
    ) -> ClipSearchIdentifier | ClipIdentifier | RecordingIdentifier | None:
        """Generate a ClipSearchIdentifier from a string."""
        return (
            ClipSearchIdentifier.from_str(data)
            or ClipIdentifier.from_str(data)
            or RecordingIdentifier.from_str(data)
        )


@attr.s(frozen=True)
class ClipIdentifier(Identifier):
    """Clip Identifier."""

    IDENTIFIER_TYPE = "clips"

    name: str = attr.ib(
        validator=[attr.validators.instance_of(str)],
    )

    def __str__(self) -> str:
        """Convert to a string."""
        return "/".join((self.IDENTIFIER_TYPE, self.name))

    @classmethod
    def from_str(cls, data: str) -> ClipIdentifier | None:
        """Generate a ClipIdentifier from a string."""
        parts = data.split("/")
        if parts[0] != cls.IDENTIFIER_TYPE:
            return None

        return cls(name=parts[1])


@attr.s(frozen=True)
class ClipSearchIdentifier(Identifier):
    """Clip Search Identifier."""

    IDENTIFIER_TYPE = "clip-search"

    name: str = attr.ib(
        default="",
        validator=[attr.validators.instance_of(str)],
    )
    after: int | None = attr.ib(
        default=None,
        converter=Identifier._to_int_or_none,
        validator=[attr.validators.instance_of((int, type(None)))],
    )
    before: int | None = attr.ib(
        default=None,
        converter=Identifier._to_int_or_none,
        validator=[attr.validators.instance_of((int, type(None)))],
    )
    camera: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )
    label: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )
    zone: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )

    @classmethod
    def from_str(cls, data: str) -> ClipSearchIdentifier | None:
        """Generate a ClipSearchIdentifier from a string."""
        parts = data.split("/")
        if parts[0] != cls.IDENTIFIER_TYPE:
            return None

        try:
            return cls(
                name=cls._get_index(parts, 1, ""),
                after=cls._get_index(parts, 2),
                before=cls._get_index(parts, 3),
                camera=cls._get_index(parts, 4),
                label=cls._get_index(parts, 5),
                zone=cls._get_index(parts, 6),
            )
        except ValueError:
            return None

    def __str__(self) -> str:
        """Convert to a string."""

        return "/".join(
            [self.IDENTIFIER_TYPE]
            + [
                self._empty_if_none(val)
                for val in (
                    self.name,
                    self.after,
                    self.before,
                    self.camera,
                    self.label,
                    self.zone,
                )
            ]
        )

    def is_root(self) -> str:
        """Determine if an identifier is a clips root."""
        return not any(
            [self.name, self.after, self.before, self.camera, self.label, self.zone]
        )


def _validate_year_month(inst: attr.s, attribute: str, data: str | None) -> None:
    """Validate input."""
    if data:
        year, month = data.split("-")
        if int(year) < 0 or int(month) <= 0 or int(month) > 12:
            raise ValueError("Invalid year-month in identifier: %s" % data)


def _validate_day(inst: attr.s, attribute: str, value: int | None):
    """Determine if a value is a valid day."""
    if value is not None and (int(value) < 1 or int(value) > 31):
        raise ValueError("Invalid day in identifier: %s" % value)


def _validate_hour(inst: attr.s, attribute: str, value: int | None):
    """Determine if a value is a valid hour."""
    if value is not None and (int(value) < 1 or int(value) > 23):
        raise ValueError("Invalid hour in identifier: %s" % value)


@attr.s(frozen=True)
class RecordingIdentifier(Identifier):
    """Recording Identifier."""

    IDENTIFIER_TYPE = "recordings"

    year_month: str | None = attr.ib(
        default=None,
        validator=[
            attr.validators.instance_of((str, type(None))),
            _validate_year_month,
        ],
    )

    day: int | None = attr.ib(
        default=None,
        converter=Identifier._to_int_or_none,
        validator=[
            attr.validators.instance_of((int, type(None))),
            _validate_day,
        ],
    )

    hour: int | None = attr.ib(
        default=None,
        converter=Identifier._to_int_or_none,
        validator=[
            attr.validators.instance_of((int, type(None))),
            _validate_hour,
        ],
    )

    camera: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )

    recording_name: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )

    @classmethod
    def from_str(cls, data: str) -> RecordingIdentifier | None:
        """Generate a RecordingIdentifier from a string."""
        parts = data.split("/")
        if parts[0] != cls.IDENTIFIER_TYPE:
            return None

        try:
            return cls(
                year_month=cls._get_index(parts, 1),
                day=cls._get_index(parts, 2),
                hour=cls._get_index(parts, 3),
                camera=cls._get_index(parts, 4),
                recording_name=cls._get_index(parts, 5),
            )
        except ValueError:
            return None

    def __str__(self) -> str:
        """Convert to a string."""
        return "/".join(
            [self.IDENTIFIER_TYPE]
            + [
                self._empty_if_none(val)
                for val in (
                    self.year_month,
                    f"{self.day:02}" if self.day is not None else None,
                    f"{self.hour:02}" if self.hour is not None else None,
                    self.camera,
                    self.recording_name,
                )
            ]
        )

    def get_frigate_server_path(self) -> str:
        """Get the equivalent Frigate server path."""

        # The attributes of this class represent a path that the recording can
        # be retrieved from the Frigate server. If there are holes in the path
        # (i.e. missing attributes) the path won't work on the Frigate server,
        # so the path returned is either complete or up until the first "hole" /
        # missing attribute.

        in_parts = [
            self.year_month,
            f"{self.day:02}" if self.day is not None else None,
            f"{self.hour:02}" if self.hour is not None else None,
            self.camera,
            self.recording_name,
        ]

        out_parts = []
        for val in in_parts:
            if val is None:
                break
            out_parts.append(str(val))
        return "/".join(out_parts)

    def get_changes_to_set_next_empty(self, data: str) -> dict[str, str]:
        """Get the changes that would set the next attribute in the hierarchy."""
        for attribute in self.__attrs_attrs__:
            if getattr(self, attribute.name) is None:
                return {attribute.name: data}
        raise ValueError("No empty attribute available")


@attr.s(frozen=True)
class EventSummaryData:
    """Summary data from Frigate events."""

    data: dict[str, Any] = attr.ib()
    cameras: list[dict[str, Any]] = attr.ib()
    labels: list[dict[str, Any]] = attr.ib()
    zones: list[dict[str, Any]] = attr.ib()

    @classmethod
    def from_raw_data(cls, summary_data: dict[str, Any]) -> None:
        """Generate an EventSummaryData object from raw data."""

        cameras = list({d["camera"] for d in summary_data})
        labels = list({d["label"] for d in summary_data})
        zones = list({zone for d in summary_data for zone in d["zones"]})
        return cls(summary_data, cameras, labels, zones)


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

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        identifier = Identifier.from_str(item.identifier)
        if identifier:
            return PlayMedia(f"/api/frigate/{identifier}", MIME_TYPE)
        raise Unresolvable("Unknown identifier: %s" % item.identifier)

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
                        identifier=ClipSearchIdentifier(),
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
                        identifier=RecordingIdentifier(),
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

        identifier = Identifier.from_str(item.identifier)

        if isinstance(identifier, ClipSearchIdentifier):
            try:
                events = await self._client.async_get_events(
                    after=identifier.after,
                    before=identifier.before,
                    camera=identifier.camera,
                    label=identifier.label,
                    zone=identifier.zone,
                    limit=10000 if identifier.name.endswith(".all") else ITEM_LIMIT,
                )
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc

            return self._browse_clips(
                await self._get_event_summary_data(), identifier, events
            )

        if isinstance(identifier, RecordingIdentifier):
            path = identifier.get_frigate_server_path()
            try:
                recordings_folder = await self._client.async_get_recordings_folder(path)
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc

            if identifier.camera:
                return self._browse_recordings(identifier, recordings_folder)
            return self._browse_recording_folders(identifier, recordings_folder)

        raise MediaSourceError("Invalid media source identifier: %s" % item.identifier)

    async def _get_event_summary_data(self) -> EventSummaryData:
        """Get event summary data."""

        try:
            summary_data = await self._client.async_get_event_summary()
        except FrigateApiClientError as exc:
            raise MediaSourceError from exc

        # Add timestamps to raw data.
        for data in summary_data:
            data["timestamp"] = int(
                dt.datetime.strptime(data["day"], "%Y-%m-%d")
                .astimezone(DEFAULT_TIME_ZONE)
                .timestamp()
            )

        return EventSummaryData.from_raw_data(summary_data)

    def _browse_clips(
        self,
        summary_data: EventSummaryData,
        identifier: ClipSearchIdentifier,
        events: dict[str, Any],
    ) -> BrowseMediaSource:
        """Browse clips."""
        count = self._count_by(summary_data, identifier)

        if identifier.is_root():
            title = f"Clips ({count})"
        else:
            title = f"{' > '.join([s for s in get_friendly_name(identifier.name).split('.') if s != '']).title()} ({count})"

        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
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
        if count > 0 and len(event_items) == ITEM_LIMIT and identifier.is_root():
            # only render if > 10% is represented in view
            if ITEM_LIMIT / float(count) > 0.1:
                base.children.extend(event_items)
        else:
            base.children.extend(event_items)

        drilldown_sources = []
        drilldown_sources.extend(
            self._build_date_sources(summary_data, identifier, len(base.children))
        )
        if not identifier.camera:
            drilldown_sources.extend(
                self._build_camera_sources(summary_data, identifier, len(base.children))
            )
        if not identifier.label:
            drilldown_sources.extend(
                self._build_label_sources(summary_data, identifier, len(base.children))
            )
        if not identifier.zone:
            drilldown_sources.extend(
                self._build_zone_sources(summary_data, identifier, len(base.children))
            )

        # only show the drill down options if there are more than 10 events
        # and there is more than 1 drilldown or when you aren't showing any events
        if len(events) > 10 and (len(drilldown_sources) > 1 or len(base.children) == 0):
            base.children.extend(drilldown_sources)

        # add an all source if there are no drilldowns available and you are at the item limit
        if (
            (len(base.children) == 0 or len(base.children) == len(event_items))
            and not identifier.name.endswith(".all")
            and len(event_items) == ITEM_LIMIT
        ):
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=attr.evolve(identifier, name=f"{identifier.name}.all"),
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
                identifier=ClipIdentifier(name=f"{event['camera']}-{event['id']}.mp4"),
                media_class=MEDIA_CLASS_VIDEO,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=f"{dt.datetime.fromtimestamp(event['start_time'], DEFAULT_TIME_ZONE).strftime(DATE_STR_FORMAT)} [{int(event['end_time']-event['start_time'])}s, {event['label'].capitalize()} {int(event['top_score']*100)}%]",
                can_play=True,
                can_expand=False,
                thumbnail=f"data:image/jpeg;base64,{event['thumbnail']}",
            )
            for event in events
        ]

    def _build_camera_sources(
        self,
        summary_data: EventSummaryData,
        identifier: ClipSearchIdentifier,
        shown_event_count: int,
    ) -> BrowseMediaSource:
        sources = []
        for camera in summary_data.cameras:
            count = self._count_by(
                summary_data,
                attr.evolve(
                    identifier,
                    camera=camera,
                ),
            )
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.{camera}",
                        camera=camera,
                    ),
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

    def _build_label_sources(
        self,
        summary_data: EventSummaryData,
        identifier: ClipSearchIdentifier,
        shown_event_count: int,
    ) -> BrowseMediaSource:
        sources = []
        for label in summary_data.labels:
            count = self._count_by(
                summary_data,
                attr.evolve(
                    identifier,
                    label=label,
                ),
            )
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.{label}",
                        label=label,
                    ),
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

    def _build_zone_sources(
        self,
        summary_data: EventSummaryData,
        identifier: ClipSearchIdentifier,
        shown_event_count: int,
    ) -> BrowseMediaSource:
        """Build zone media sources."""
        sources = []
        for zone in summary_data.zones:
            count = self._count_by(summary_data, attr.evolve(identifier, zone=zone))
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.{zone}",
                        zone=zone,
                    ),
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

    def _build_date_sources(
        self,
        summary_data: EventSummaryData,
        identifier: ClipSearchIdentifier,
        shown_event_count: int,
    ) -> BrowseMediaSource:
        """Build data media sources."""
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
            summary_data, attr.evolve(identifier, after=start_of_today)
        )

        count_yesterday = self._count_by(
            summary_data,
            attr.evolve(
                identifier,
                after=start_of_yesterday,
                before=start_of_today,
            ),
        )
        count_this_month = self._count_by(
            summary_data,
            attr.evolve(
                identifier,
                after=start_of_month,
            ),
        )
        count_last_month = self._count_by(
            summary_data,
            attr.evolve(
                identifier,
                after=start_of_last_month,
                before=start_of_month,
            ),
        )
        count_this_year = self._count_by(
            summary_data,
            attr.evolve(
                identifier,
                after=start_of_year,
            ),
        )

        # if a date range has already been selected
        if identifier.before or identifier.after:
            before = identifier.before if identifier.before else int(now.timestamp())
            after = identifier.after if identifier.after else int(now.timestamp())

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
                        summary_data,
                        attr.evolve(
                            identifier,
                            after=start_of_current_month,
                            before=start_of_next_month,
                        ),
                    )
                    sources.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=attr.evolve(
                                identifier,
                                name=f"{identifier.name}.{current_date.strftime('%Y-%m')}",
                                after=start_of_current_month,
                                before=start_of_next_month,
                            ),
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
                        summary_data,
                        attr.evolve(
                            identifier,
                            after=start_of_current_day,
                            before=start_of_next_day,
                        ),
                    )
                    if count_current > 0:
                        sources.append(
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=attr.evolve(
                                    identifier,
                                    name=f"{identifier.name}.{current_date.strftime('%Y-%m-%d')}",
                                    after=start_of_current_day,
                                    before=start_of_next_day,
                                ),
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
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.today",
                        after=start_of_today,
                    ),
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
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.yesterday",
                        after=start_of_yesterday,
                        before=start_of_today,
                    ),
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
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.this_month",
                        after=start_of_month,
                    ),
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
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.last_month",
                        after=start_of_last_month,
                        before=start_of_month,
                    ),
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
                    identifier=attr.evolve(
                        identifier,
                        name=f"{identifier.name}.this_year",
                        after=start_of_year,
                    ),
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

    def _count_by(
        self, summary_data: EventSummaryData, identifier: ClipSearchIdentifier
    ) -> int:
        """Return count of events that match the identifier."""
        return sum(
            [
                d["count"]
                for d in summary_data.data
                if (
                    (identifier.after is None or d["timestamp"] >= identifier.after)
                    and (
                        identifier.before is None or d["timestamp"] < identifier.before
                    )
                    and (identifier.camera is None or identifier.camera in d["camera"])
                    and (identifier.label is None or identifier.label in d["label"])
                    and (identifier.zone is None or identifier.zone in d["zones"])
                )
            ]
        )

    @classmethod
    def _generate_recording_title(
        cls, identifier: RecordingIdentifier, folder: str = None
    ) -> str | None:
        """Generate recording title."""
        try:
            if identifier.camera:
                if folder is None:
                    return get_friendly_name(identifier.camera)
                minute_seconds = folder["name"].replace(".mp4", "")
                return dt.datetime.strptime(
                    f"{identifier.hour}.{minute_seconds}", "%H.%M.%S"
                ).strftime("%T")

            if identifier.hour:
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier.hour}.00.00", "%H.%M.%S"
                    ).strftime("%T")
                return get_friendly_name(folder["name"])

            if identifier.day:
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier.year_month}-{identifier.day}", "%Y-%m-%d"
                    ).strftime("%B %d")
                return dt.datetime.strptime(
                    f"{folder['name']}.00.00", "%H.%M.%S"
                ).strftime("%T")

            if identifier.year_month:
                if folder is None:
                    return dt.datetime.strptime(
                        f"{identifier.year_month}", "%Y-%m"
                    ).strftime("%B %Y")
                return dt.datetime.strptime(
                    f"{identifier.year_month}-{folder['name']}", "%Y-%m-%d"
                ).strftime("%B %d")

            if folder is None:
                return "Recordings"
            return dt.datetime.strptime(f"{folder['name']}", "%Y-%m").strftime("%B %Y")
        except ValueError:
            return None

    def _get_recording_base_media_source(
        self, identifier: RecordingIdentifier
    ) -> BrowseMediaSource:
        """Get the base BrowseMediaSource object for a recording identifier."""
        title = self._generate_recording_title(identifier)

        # Must be able to generate a title for the source folder.
        if not title:
            raise MediaSourceError

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
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
        self, identifier: RecordingIdentifier, folders: dict[str, Any]
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
                    identifier=attr.evolve(
                        identifier,
                        **identifier.get_changes_to_set_next_empty(folder["name"]),
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
        self, identifier: RecordingIdentifier, recordings: dict[str, Any]
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
                    identifier=attr.evolve(
                        identifier, recording_name=recording["name"]
                    ),
                    media_class=MEDIA_CLASS_VIDEO,
                    media_content_type=MEDIA_TYPE_VIDEO,
                    title=title,
                    can_play=True,
                    can_expand=False,
                    thumbnail=None,
                )
            )
        return base
