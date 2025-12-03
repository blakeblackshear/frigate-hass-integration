"""Frigate Media Source."""

from __future__ import annotations

import datetime as dt
import enum
import logging
from typing import Any, cast

import attr
from dateutil.relativedelta import relativedelta

from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import system_info
from homeassistant.helpers.template import DATE_STR_FORMAT
from homeassistant.util.dt import DEFAULT_TIME_ZONE, async_get_time_zone

from . import get_friendly_name
from .api import FrigateApiClient, FrigateApiClientError
from .const import CONF_MEDIA_BROWSER_ENABLE, DEFAULT_VOD_EVENT_PADDING, DOMAIN, NAME
from .views import (
    get_client_for_frigate_instance_id,
    get_config_entry_for_frigate_instance_id,
    get_default_config_entry,
    get_frigate_instance_id_for_config_entry,
)

_LOGGER = logging.getLogger(__name__)

ITEM_LIMIT = 50
SECONDS_IN_DAY = 60 * 60 * 24
SECONDS_IN_MONTH = SECONDS_IN_DAY * 31


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up Frigate media source."""
    return FrigateMediaSource(hass)


class FrigateBrowseMediaMetadata:
    """Metadata for browsable Frigate media files."""

    event: dict[str, Any] | None

    def __init__(self, event: dict[str, Any]):
        """Initialize a FrigateBrowseMediaMetadata object."""
        self.event = event

    def as_dict(self) -> dict:
        """Convert the object to a dictionary."""
        return {"event": self.event}


class FrigateBrowseMediaSource(BrowseMediaSource):
    """Represent a browsable Frigate media file."""

    children: list[FrigateBrowseMediaSource] | None
    frigate: FrigateBrowseMediaMetadata

    def as_dict(self, *args: Any, **kwargs: Any) -> dict:
        """Convert the object to a dictionary."""
        res: dict = super().as_dict(*args, **kwargs)
        res["frigate"] = self.frigate.as_dict()
        return res

    def __init__(
        self, frigate: FrigateBrowseMediaMetadata, *args: Any, **kwargs: Any
    ) -> None:
        """Initialize media source browse media."""
        super().__init__(*args, **kwargs)
        self.frigate = frigate


@attr.s(frozen=True)
class Identifier:
    """Base class for Identifiers."""

    frigate_instance_id: str = attr.ib(
        validator=[attr.validators.instance_of(str)],
    )

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
    def from_str(
        cls,
        data: str,
        default_frigate_instance_id: str | None = None,
    ) -> EventSearchIdentifier | EventIdentifier | RecordingIdentifier | None:
        """Generate a EventSearchIdentifier from a string."""
        return (
            EventSearchIdentifier.from_str(data, default_frigate_instance_id)
            or EventIdentifier.from_str(data, default_frigate_instance_id)
            or RecordingIdentifier.from_str(data, default_frigate_instance_id)
        )

    @classmethod
    def get_identifier_type(cls) -> str:
        """Get the identifier type."""
        raise NotImplementedError

    def get_integration_proxy_path(self, tz_info: dt.tzinfo) -> str:
        """Get the proxy (Home Assistant view) path for this identifier."""
        raise NotImplementedError

    @classmethod
    def _add_frigate_instance_id_to_parts_if_absent(
        cls, parts: list[str], default_frigate_instance_id: str | None = None
    ) -> list[str]:
        """Add a frigate instance id if it's not specified."""
        if (
            cls._get_index(parts, 0) == cls.get_identifier_type()
            and default_frigate_instance_id is not None
        ):
            parts.insert(0, default_frigate_instance_id)
        return parts

    @property
    def mime_type(self) -> str:
        """Get mime type for this identifier."""
        raise NotImplementedError

    @property
    def media_type(self) -> str:
        """Get media type for this identifier."""
        raise NotImplementedError

    @property
    def media_class(self) -> str:
        """Get media class for this identifier."""
        raise NotImplementedError


class FrigateMediaType(enum.Enum):
    """Type of media this identifier represents."""

    CLIPS = "clips"
    SNAPSHOTS = "snapshots"

    @property
    def mime_type(self) -> str:
        """Get mime type for this frigate media type."""
        if self == FrigateMediaType.CLIPS:
            return "application/x-mpegURL"
        return "image/jpg"

    @property
    def media_type(self) -> str:
        """Get media type for this frigate media type."""
        if self == FrigateMediaType.CLIPS:
            return str(MediaType.VIDEO)
        return str(MediaType.IMAGE)

    @property
    def media_class(self) -> str:
        """Get media class for this frigate media type."""
        if self == FrigateMediaType.CLIPS:
            return str(MediaClass.VIDEO)
        return str(MediaClass.IMAGE)

    @property
    def extension(self) -> str:
        """Get filename extension."""
        if self == FrigateMediaType.CLIPS:
            return "m3u8"
        return "jpg"


@attr.s(frozen=True)
class EventIdentifier(Identifier):
    """Event Identifier (clip or snapshot)."""

    frigate_media_type: FrigateMediaType = attr.ib(
        validator=[attr.validators.in_(FrigateMediaType)]
    )

    id: str = attr.ib(
        validator=[attr.validators.instance_of(str)],
    )

    camera: str = attr.ib(
        validator=[attr.validators.instance_of(str)],
    )

    def __str__(self) -> str:
        """Convert to a string."""
        return "/".join(
            (
                self.frigate_instance_id,
                self.get_identifier_type(),
                self.frigate_media_type.value,
                self.camera,
                self.id,
            )
        )

    @classmethod
    def from_str(
        cls, data: str, default_frigate_instance_id: str | None = None
    ) -> EventIdentifier | None:
        """Generate a EventIdentifier from a string."""
        parts = cls._add_frigate_instance_id_to_parts_if_absent(
            data.split("/"), default_frigate_instance_id
        )

        if len(parts) != 5 or parts[1] != cls.get_identifier_type():
            return None

        try:
            return cls(
                frigate_instance_id=parts[0],
                frigate_media_type=FrigateMediaType(parts[2]),
                camera=parts[3],
                id=parts[4],
            )
        except ValueError:
            return None

    @classmethod
    def get_identifier_type(cls) -> str:
        """Get the identifier type."""
        return "event"

    def get_integration_proxy_path(self, tz_info: dt.tzinfo) -> str:
        """Get the equivalent Frigate server path."""
        if self.frigate_media_type == FrigateMediaType.CLIPS:
            return f"vod/event/{self.id}/index.{self.frigate_media_type.extension}"
        return f"snapshot/{self.id}"

    @property
    def mime_type(self) -> str:
        """Get mime type for this identifier."""
        return self.frigate_media_type.mime_type


def _to_int_or_none(data: str | int) -> int | None:
    """Convert to an integer or None."""
    return int(data) if data is not None else None


@attr.s(frozen=True)
class EventSearchIdentifier(Identifier):
    """Event Search Identifier."""

    frigate_media_type: FrigateMediaType = attr.ib(
        validator=[attr.validators.in_(FrigateMediaType)]
    )
    name: str = attr.ib(
        default="",
        validator=[attr.validators.instance_of(str)],
    )
    after: int | None = attr.ib(
        default=None,
        converter=_to_int_or_none,
        validator=[attr.validators.instance_of((int, type(None)))],
    )
    before: int | None = attr.ib(
        default=None,
        converter=_to_int_or_none,
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
    def from_str(
        cls, data: str, default_frigate_instance_id: str | None = None
    ) -> EventSearchIdentifier | None:
        """Generate a EventSearchIdentifier from a string."""
        parts = cls._add_frigate_instance_id_to_parts_if_absent(
            data.split("/"), default_frigate_instance_id
        )

        if len(parts) < 3 or parts[1] != cls.get_identifier_type():
            return None

        try:
            return cls(
                frigate_instance_id=cls._get_index(parts, 0),
                frigate_media_type=FrigateMediaType(cls._get_index(parts, 2)),
                name=cls._get_index(parts, 3, ""),
                after=cls._get_index(parts, 4),
                before=cls._get_index(parts, 5),
                camera=cls._get_index(parts, 6),
                label=cls._get_index(parts, 7),
                zone=cls._get_index(parts, 8),
            )
        except ValueError:
            return None

    def __str__(self) -> str:
        """Convert to a string."""

        return "/".join(
            [self.frigate_instance_id, self.get_identifier_type()]
            + [
                self._empty_if_none(val)
                for val in (
                    self.frigate_media_type.value,
                    self.name,
                    self.after,
                    self.before,
                    self.camera,
                    self.label,
                    self.zone,
                )
            ]
        )

    def is_root(self) -> bool:
        """Determine if an identifier is an event root for a given server."""
        return not any(
            [self.name, self.after, self.before, self.camera, self.label, self.zone]
        )

    @classmethod
    def get_identifier_type(cls) -> str:
        """Get the identifier type."""
        return "event-search"

    @property
    def media_type(self) -> str:
        """Get mime type for this identifier."""
        return self.frigate_media_type.media_type

    @property
    def media_class(self) -> str:
        """Get media class for this identifier."""
        return self.frigate_media_type.media_class


def _validate_year_month_day(
    inst: RecordingIdentifier, attribute: attr.Attribute, data: str | None
) -> None:
    """Validate input."""
    if data:
        try:
            dt.datetime.strptime(data, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid date in identifier: {data}") from exc


def _validate_hour(
    inst: RecordingIdentifier, attribute: attr.Attribute, value: int | None
) -> None:
    """Determine if a value is a valid hour."""
    if value is not None and (int(value) < 0 or int(value) > 23):
        raise ValueError(f"Invalid hour in identifier: {value}")


@attr.s(frozen=True)
class RecordingIdentifier(Identifier):
    """Recording Identifier."""

    camera: str | None = attr.ib(
        default=None, validator=[attr.validators.instance_of((str, type(None)))]
    )

    year_month_day: str | None = attr.ib(
        default=None,
        validator=[
            attr.validators.instance_of((str, type(None))),
            _validate_year_month_day,
        ],
    )

    hour: int | None = attr.ib(
        default=None,
        converter=_to_int_or_none,
        validator=[
            attr.validators.instance_of((int, type(None))),
            _validate_hour,
        ],
    )

    @classmethod
    def from_str(
        cls, data: str, default_frigate_instance_id: str | None = None
    ) -> RecordingIdentifier | None:
        """Generate a RecordingIdentifier from a string."""
        parts = cls._add_frigate_instance_id_to_parts_if_absent(
            data.split("/"), default_frigate_instance_id
        )

        if len(parts) < 2 or parts[1] != cls.get_identifier_type():
            return None

        try:
            return cls(
                frigate_instance_id=parts[0],
                camera=cls._get_index(parts, 2),
                year_month_day=cls._get_index(parts, 3),
                hour=cls._get_index(parts, 4),
            )
        except ValueError:
            return None

    def __str__(self) -> str:
        """Convert to a string."""
        return "/".join(
            [self.frigate_instance_id, self.get_identifier_type()]
            + [
                self._empty_if_none(val)
                for val in (
                    self.camera,
                    (
                        f"{self.year_month_day}"
                        if self.year_month_day is not None
                        else None
                    ),
                    f"{self.hour:02}" if self.hour is not None else None,
                )
            ]
        )

    @classmethod
    def get_identifier_type(cls) -> str:
        """Get the identifier type."""
        return "recordings"

    def get_integration_proxy_path(self, tz_info: dt.tzinfo) -> str:
        """Get the integration path that will proxy this identifier."""

        if (
            self.camera is not None
            and self.year_month_day is not None
            and self.hour is not None
        ):
            year, month, day = self.year_month_day.split("-")
            # Take the selected time in users local time and find the offset to
            # UTC, convert to UTC then request the vod for that time.
            start_date: dt.datetime = dt.datetime(
                int(year),
                int(month),
                int(day),
                int(self.hour),
                tzinfo=dt.UTC,
            ) - (dt.datetime.now(tz_info).utcoffset() or dt.timedelta())

            parts = [
                "vod",
                f"{start_date.year}-{start_date.month:02}",
                f"{start_date.day:02}",
                f"{start_date.hour:02}",
                self.camera,
                "utc",
                "index.m3u8",
            ]

            return "/".join(parts)

        raise MediaSourceError(
            "Can not get proxy-path without year_month_day and hour."
        )

    @property
    def mime_type(self) -> str:
        """Get mime type for this identifier."""
        return "application/x-mpegURL"

    @property
    def media_class(self) -> str:
        """Get media class for this identifier."""
        return str(MediaClass.MOVIE)

    @property
    def media_type(self) -> str:
        """Get media type for this identifier."""
        return str(MediaType.VIDEO)


@attr.s(frozen=True)
class EventSummaryData:
    """Summary data from Frigate events."""

    data: list[dict[str, Any]] = attr.ib()
    cameras: list[str] = attr.ib()
    labels: list[str] = attr.ib()
    zones: list[str] = attr.ib()

    @classmethod
    def from_raw_data(cls, summary_data: list[dict[str, Any]]) -> EventSummaryData:
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

    def _is_allowed_as_media_source(self, instance_id: str) -> bool:
        """Whether a given frigate instance is allowed as a media source."""
        config_entry = get_config_entry_for_frigate_instance_id(self.hass, instance_id)
        return (
            config_entry.options.get(CONF_MEDIA_BROWSER_ENABLE, True) is True
            if config_entry
            else False
        )

    def _get_client(self, identifier: Identifier) -> FrigateApiClient:
        """Get client for a given identifier."""
        client = get_client_for_frigate_instance_id(
            self.hass, identifier.frigate_instance_id
        )
        if client:
            return client

        raise MediaSourceError(
            "Could not find client for frigate instance "
            f"id: {identifier.frigate_instance_id}"
        )

    def _get_default_frigate_instance_id(self) -> str | None:
        """Get the default frigate_instance_id if any."""
        default_config_entry = get_default_config_entry(self.hass)
        if default_config_entry:
            return get_frigate_instance_id_for_config_entry(
                self.hass, default_config_entry
            )
        return None

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        identifier = Identifier.from_str(
            item.identifier,
            default_frigate_instance_id=self._get_default_frigate_instance_id(),
        )
        if identifier and self._is_allowed_as_media_source(
            identifier.frigate_instance_id
        ):
            info = await system_info.async_get_system_info(self.hass)
            tz_name = info.get("timezone", "utc")
            tz_info = await async_get_time_zone(tz_name)
            if not tz_info:
                raise Unresolvable(
                    f"Could not get timezone object for timezone: {tz_name}"
                )

            # For event clips, fetch event data and use timestamp-based VOD with padding
            if (
                isinstance(identifier, EventIdentifier)
                and identifier.frigate_media_type == FrigateMediaType.CLIPS
            ):
                try:
                    client = self._get_client(identifier)
                    event = await client.async_get_event(identifier.id)

                    start_time = event.get("start_time")
                    end_time = event.get("end_time")

                    if start_time is not None:
                        padded_start = int(start_time - DEFAULT_VOD_EVENT_PADDING)

                        if end_time is not None:
                            padded_end = int(end_time + DEFAULT_VOD_EVENT_PADDING)
                        else:
                            padded_end = int(
                                dt.datetime.now(DEFAULT_TIME_ZONE).timestamp()
                            )

                        server_path = f"vod/{identifier.camera}/start/{padded_start}/end/{padded_end}/index.m3u8"
                        return PlayMedia(
                            f"/api/frigate/{identifier.frigate_instance_id}/{server_path}",
                            identifier.mime_type,
                        )
                except FrigateApiClientError as exc:
                    _LOGGER.warning("Failed to fetch event %s: %s", identifier.id, exc)

            server_path = identifier.get_integration_proxy_path(tz_info)
            return PlayMedia(
                f"/api/frigate/{identifier.frigate_instance_id}/{server_path}",
                identifier.mime_type,
            )
        raise Unresolvable(f"Unknown or disallowed identifier: {item.identifier}")

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Browse media."""

        if not item.identifier:
            base = BrowseMediaSource(
                domain=DOMAIN,
                identifier="",
                media_class=MediaClass.DIRECTORY,
                children_media_class=MediaClass.VIDEO,
                media_content_type=MediaType.VIDEO,
                title=NAME,
                can_play=False,
                can_expand=True,
                thumbnail=None,
                children=[],
            )
            base.children = []
            for config_entry in self.hass.config_entries.async_entries(DOMAIN):
                frigate_instance_id = get_frigate_instance_id_for_config_entry(
                    self.hass, config_entry
                )
                if frigate_instance_id and self._is_allowed_as_media_source(
                    frigate_instance_id
                ):
                    clips_identifier = EventSearchIdentifier(
                        frigate_instance_id, FrigateMediaType.CLIPS
                    )
                    recording_identifier = RecordingIdentifier(frigate_instance_id)
                    snapshots_identifier = EventSearchIdentifier(
                        frigate_instance_id, FrigateMediaType.SNAPSHOTS
                    )
                    # Use the media class of the children to help distinguish
                    # the icons in the frontend.
                    base.children.extend(
                        [
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=str(clips_identifier),
                                media_class=MediaClass.DIRECTORY,
                                children_media_class=clips_identifier.media_class,
                                media_content_type=clips_identifier.media_type,
                                title=f"Clips [{config_entry.title}]",
                                can_play=False,
                                can_expand=True,
                                thumbnail=None,
                                children=[],
                            ),
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=str(recording_identifier),
                                media_class=MediaClass.DIRECTORY,
                                children_media_class=recording_identifier.media_class,
                                media_content_type=recording_identifier.media_type,
                                title=f"Recordings [{config_entry.title}]",
                                can_play=False,
                                can_expand=True,
                                thumbnail=None,
                                children=[],
                            ),
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=str(snapshots_identifier),
                                media_class=MediaClass.DIRECTORY,
                                children_media_class=snapshots_identifier.media_class,
                                media_content_type=snapshots_identifier.media_type,
                                title=f"Snapshots [{config_entry.title}]",
                                can_play=False,
                                can_expand=True,
                                thumbnail=None,
                                children=[],
                            ),
                        ],
                    )
            return base

        identifier = Identifier.from_str(
            item.identifier,
            default_frigate_instance_id=self._get_default_frigate_instance_id(),
        )

        if identifier is not None and not self._is_allowed_as_media_source(
            identifier.frigate_instance_id
        ):
            raise MediaSourceError(
                f"Forbidden media source identifier: {item.identifier}"
            )

        if isinstance(identifier, EventSearchIdentifier):
            if identifier.frigate_media_type == FrigateMediaType.CLIPS:
                media_kwargs = {"has_clip": True}
            else:
                media_kwargs = {"has_snapshot": True}
            try:
                events = await self._get_client(identifier).async_get_events(
                    after=identifier.after,
                    before=identifier.before,
                    cameras=[identifier.camera] if identifier.camera else None,
                    labels=[identifier.label] if identifier.label else None,
                    sub_labels=None,
                    zones=[identifier.zone] if identifier.zone else None,
                    limit=10000 if identifier.name.endswith(".all") else ITEM_LIMIT,
                    **media_kwargs,
                )
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc

            return self._browse_events(
                await self._get_event_summary_data(identifier), identifier, events
            )

        if isinstance(identifier, RecordingIdentifier):
            try:
                if not identifier.camera:
                    config = await self._get_client(identifier).async_get_config()
                    return self._get_camera_recording_folders(identifier, config)

                info = await system_info.async_get_system_info(self.hass)
                recording_summary = cast(
                    list[dict[str, Any]],
                    await self._get_client(identifier).async_get_recordings_summary(
                        camera=identifier.camera, timezone=info.get("timezone", "utc")
                    ),
                )

                if not identifier.year_month_day:
                    return self._get_recording_days(identifier, recording_summary)

                return self._get_recording_hours(identifier, recording_summary)
            except FrigateApiClientError as exc:
                raise MediaSourceError from exc

        raise MediaSourceError(f"Invalid media source identifier: {item.identifier}")

    async def _get_event_summary_data(
        self, identifier: EventSearchIdentifier
    ) -> EventSummaryData:
        """Get event summary data."""

        try:
            info = await system_info.async_get_system_info(self.hass)

            if identifier.frigate_media_type == FrigateMediaType.CLIPS:
                kwargs = {"has_clip": True}
            else:
                kwargs = {"has_snapshot": True}
            summary_data = await self._get_client(identifier).async_get_event_summary(
                timezone=info.get("timezone", "utc"), **kwargs
            )
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

    def _browse_events(
        self,
        summary_data: EventSummaryData,
        identifier: EventSearchIdentifier,
        events: list[dict[str, Any]],
    ) -> BrowseMediaSource:
        """Browse events."""
        count = self._count_by(summary_data, identifier)

        if identifier.is_root():
            title = f"{identifier.frigate_media_type.value.capitalize()} ({count})"
        else:
            title = f"{' > '.join([s for s in get_friendly_name(identifier.name).split('.') if s != '']).title()} ({count})"

        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=str(identifier),
            media_class=MediaClass.DIRECTORY,
            children_media_class=identifier.media_class,
            media_content_type=identifier.media_type,
            title=title,
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=[],
        )
        base.children = []

        event_items = self._build_event_response(identifier, events)

        # if you are at the limit, but not at the root
        if count > 0 and len(event_items) == ITEM_LIMIT and identifier.is_root():
            # only render if > 10% is represented in view
            if ITEM_LIMIT / float(count) > 0.1:
                base.children.extend(event_items)
        else:
            base.children.extend(event_items)

        drilldown_sources: list[BrowseMediaSource] = []
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
                    identifier=str(
                        attr.evolve(identifier, name=f"{identifier.name}.all")
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
                    title=f"All ({count})",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return base

    @classmethod
    def _build_event_response(
        cls, identifier: EventSearchIdentifier, events: list[dict[str, Any]]
    ) -> list[FrigateBrowseMediaSource]:
        children: list[FrigateBrowseMediaSource] = []
        for event in events:
            start_time = event.get("start_time")
            end_time = event.get("end_time")
            if start_time is None:
                continue

            if end_time is None:
                # Events that are in progress will not yet have an end_time, so
                # the duration is shown as the current time minus the start
                # time.
                duration = int(
                    dt.datetime.now(DEFAULT_TIME_ZONE).timestamp() - start_time
                )
            else:
                duration = int(end_time - start_time)

            children.append(
                FrigateBrowseMediaSource(
                    domain=DOMAIN,
                    identifier=str(
                        EventIdentifier(
                            identifier.frigate_instance_id,
                            frigate_media_type=identifier.frigate_media_type,
                            camera=event["camera"],
                            id=event["id"],
                        )
                    ),
                    media_class=identifier.media_class,
                    media_content_type=identifier.media_type,
                    title=f"{dt.datetime.fromtimestamp(event['start_time'], DEFAULT_TIME_ZONE).strftime(DATE_STR_FORMAT)} [{duration}s, {event['label'].capitalize()} {int((event['data'].get('top_score') or event['top_score'] or 0) * 100)}%]",
                    can_play=identifier.media_type == MediaType.VIDEO,
                    can_expand=False,
                    thumbnail=f"/api/frigate/{identifier.frigate_instance_id}/thumbnail/{event['id']}",
                    frigate=FrigateBrowseMediaMetadata(event=event),
                )
            )
        return children

    def _build_camera_sources(
        self,
        summary_data: EventSummaryData,
        identifier: EventSearchIdentifier,
        shown_event_count: int,
    ) -> list[BrowseMediaSource]:
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.{camera}",
                            camera=camera,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
        identifier: EventSearchIdentifier,
        shown_event_count: int,
    ) -> list[BrowseMediaSource]:
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.{label}",
                            label=label,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
        identifier: EventSearchIdentifier,
        shown_event_count: int,
    ) -> list[BrowseMediaSource]:
        """Build zone media sources."""
        sources = []
        for zone in summary_data.zones:
            count = self._count_by(summary_data, attr.evolve(identifier, zone=zone))
            if count in (0, shown_event_count):
                continue
            sources.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.{zone}",
                            zone=zone,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
        identifier: EventSearchIdentifier,
        shown_event_count: int,
    ) -> list[BrowseMediaSource]:
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
                            identifier=str(
                                attr.evolve(
                                    identifier,
                                    name=f"{identifier.name}.{current_date.strftime('%Y-%m')}",
                                    after=start_of_current_month,
                                    before=start_of_next_month,
                                )
                            ),
                            media_class=MediaClass.DIRECTORY,
                            children_media_class=MediaClass.DIRECTORY,
                            media_content_type=identifier.media_type,
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
                                identifier=str(
                                    attr.evolve(
                                        identifier,
                                        name=f"{identifier.name}.{current_date.strftime('%Y-%m-%d')}",
                                        after=start_of_current_day,
                                        before=start_of_next_day,
                                    )
                                ),
                                media_class=MediaClass.DIRECTORY,
                                children_media_class=MediaClass.DIRECTORY,
                                media_content_type=identifier.media_type,
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.today",
                            after=start_of_today,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.yesterday",
                            after=start_of_yesterday,
                            before=start_of_today,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.this_month",
                            after=start_of_month,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.last_month",
                            after=start_of_last_month,
                            before=start_of_month,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
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
                    identifier=str(
                        attr.evolve(
                            identifier,
                            name=f"{identifier.name}.this_year",
                            after=start_of_year,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
                    title="This Year",
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return sources

    def _count_by(
        self, summary_data: EventSummaryData, identifier: EventSearchIdentifier
    ) -> int:
        """Return count of events that match the identifier."""
        return sum(
            d["count"]
            for d in summary_data.data
            if (identifier.after is None or d["timestamp"] >= identifier.after)
            and (identifier.before is None or d["timestamp"] < identifier.before)
            and (identifier.camera is None or identifier.camera in d["camera"])
            and (identifier.label is None or identifier.label in d["label"])
            and (identifier.zone is None or identifier.zone in d["zones"])
        )

    def _get_recording_base_media_source(
        self, identifier: RecordingIdentifier
    ) -> BrowseMediaSource:
        """Get the base BrowseMediaSource object for a recording identifier."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=str(identifier),
            media_class=MediaClass.DIRECTORY,
            children_media_class=MediaClass.DIRECTORY,
            media_content_type=identifier.media_type,
            title="Recordings",
            can_play=False,
            can_expand=True,
            thumbnail=None,
            children=[],
        )

    def _get_camera_recording_folders(
        self, identifier: RecordingIdentifier, config: dict[str, dict]
    ) -> BrowseMediaSource:
        """List cameras for recordings."""
        base = self._get_recording_base_media_source(identifier)
        base.children = []

        for camera in config["cameras"].keys():
            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=str(
                        attr.evolve(
                            identifier,
                            camera=camera,
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
                    title=get_friendly_name(camera),
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return base

    def _get_recording_days(
        self, identifier: RecordingIdentifier, recording_days: list[dict[str, Any]]
    ) -> BrowseMediaSource:
        """List year-month-day options for camera."""
        base = self._get_recording_base_media_source(identifier)
        base.children = []

        for day_item in recording_days:
            try:
                dt.datetime.strptime(day_item["day"], "%Y-%m-%d")
            except ValueError as exc:
                raise MediaSourceError(
                    f"Media source is not valid for {identifier} {day_item['day']}"
                ) from exc

            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=str(
                        attr.evolve(
                            identifier,
                            year_month_day=day_item["day"],
                        )
                    ),
                    media_class=MediaClass.DIRECTORY,
                    children_media_class=MediaClass.DIRECTORY,
                    media_content_type=identifier.media_type,
                    title=day_item["day"],
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )

        return base

    def _get_recording_hours(
        self, identifier: RecordingIdentifier, recording_days: list[dict[str, Any]]
    ) -> BrowseMediaSource:
        """Browse Frigate recordings."""
        base = self._get_recording_base_media_source(identifier)
        base.children = []

        hour_items: list[dict[str, Any]] = next(
            (
                hours["hours"]
                for hours in recording_days
                if hours["day"] == identifier.year_month_day
            ),
            [],
        )

        for hour_data in hour_items:
            try:
                title = dt.datetime.strptime(hour_data["hour"], "%H").strftime("%H:00")
            except ValueError as exc:
                raise MediaSourceError(
                    f"Media source is not valid for {identifier} {hour_data['hour']}"
                ) from exc

            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=str(attr.evolve(identifier, hour=hour_data["hour"])),
                    media_class=identifier.media_class,
                    media_content_type=identifier.media_type,
                    title=title,
                    can_play=True,
                    can_expand=False,
                    thumbnail=None,
                )
            )
        return base
