"""Test Frigate Media Source."""
from __future__ import annotations

from collections.abc import Generator
import copy
import datetime
import json
import logging
import os
from typing import Any
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import pytz

from custom_components.frigate.api import FrigateApiClient, FrigateApiClientError
from custom_components.frigate.const import (
    ATTR_CLIENT_ID,
    ATTR_MQTT,
    CONF_MEDIA_BROWSER_ENABLE,
    DOMAIN,
)
from custom_components.frigate.media_source import (
    EventIdentifier,
    EventSearchIdentifier,
    FrigateMediaType,
    Identifier,
    RecordingIdentifier,
    async_get_media_source,
)
from homeassistant.components import media_source
from homeassistant.components.media_source import const
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import system_info

from . import (
    TEST_CONFIG,
    TEST_FRIGATE_INSTANCE_ID,
    TEST_URL,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


def _get_fixed_datetime() -> datetime.datetime:
    """Get a fixed-in-time datetime."""
    datetime_today = Mock(wraps=datetime.datetime)
    datetime_today.now = Mock(
        return_value=datetime.datetime(
            2021, 6, 4, 0, 0, 30, tzinfo=datetime.timezone.utc
        )
    )
    return datetime_today


TODAY = _get_fixed_datetime()
DRILLDOWN_BASE: dict[str, Any] = {
    "media_class": "directory",
    "media_content_type": "video",
    "can_play": False,
    "can_expand": True,
    "children_media_class": "directory",
    "thumbnail": None,
}
EVENTS_FIXTURE_FILE = "events_front_door.json"


@pytest.fixture(name="frigate_client")
def fixture_frigate_client() -> Generator[FrigateApiClient, None, None]:
    """Fixture that creates a frigate client."""

    def load_json(filename: str) -> Any:
        """Load json from a file."""
        path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)

    client = create_mock_frigate_client()
    client.async_get_events = AsyncMock(return_value=load_json(EVENTS_FIXTURE_FILE))
    yield client


async def test_async_disabled_browse_media(hass: HomeAssistant) -> None:
    """Test disabled browse media."""

    config_entry = create_mock_frigate_config_entry(
        hass,
        options={CONF_MEDIA_BROWSER_ENABLE: False},
    )
    await setup_mock_frigate_config_entry(hass, config_entry)

    # Test on an empty identifier (won't raise an exception, but won't return
    # any children).
    result = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}",
    )
    assert not result.children

    # Test on an forbidden identifier. Will raise.
    with pytest.raises(MediaSourceError) as exc:
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/event/clips/camera/CLIP-FOO",
        )
    assert "Forbidden media source identifier" in str(exc.value)


async def test_async_browse_media_root(hass: HomeAssistant) -> None:
    """Test successful browse media root."""

    # Create the default test Frigate instance.
    await setup_mock_frigate_config_entry(hass)

    # Create an additional test Frigate instance with a different config.
    another_config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    another_config[ATTR_MQTT][ATTR_CLIENT_ID] = "another_client_id"
    another_client = create_mock_frigate_client()
    another_client.async_get_config = AsyncMock(return_value=another_config)

    await setup_mock_frigate_config_entry(
        hass,
        config_entry=create_mock_frigate_config_entry(
            hass,
            entry_id="another_config_entry_id",
            data={CONF_URL: "http://somewhere.else"},
            title="http://somewhere.else",
        ),
        client=another_client,
    )

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}",
    )

    assert media.as_dict() == {
        "title": "Frigate",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                "title": f"Clips [{TEST_URL}]",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/event-search/clips//////"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "video",
                "thumbnail": None,
            },
            {
                "title": f"Recordings [{TEST_URL}]",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings///"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "movie",
                "thumbnail": None,
            },
            {
                "title": f"Snapshots [{TEST_URL}]",
                "media_class": "directory",
                "media_content_type": "image",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/event-search/snapshots//////"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "image",
                "thumbnail": None,
            },
            {
                "title": "Clips [http://somewhere.else]",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": (
                    "media-source://frigate/another_client_id/event-search/clips//////"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "video",
                "thumbnail": None,
            },
            {
                "title": "Recordings [http://somewhere.else]",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": (
                    "media-source://frigate/another_client_id/recordings///"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "movie",
                "thumbnail": None,
            },
            {
                "title": "Snapshots [http://somewhere.else]",
                "media_class": "directory",
                "media_content_type": "image",
                "media_content_id": (
                    "media-source://frigate/another_client_id"
                    "/event-search/snapshots//////"
                ),
                "can_play": False,
                "can_expand": True,
                "children_media_class": "image",
                "thumbnail": None,
            },
        ],
    }


async def test_async_browse_media_clip_search_root(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test browsing the media clips root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    with patch("custom_components.frigate.media_source.dt.datetime", new=TODAY):
        media = await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/event-search/clips",
        )

    assert len(media.as_dict()["children"]) == 58
    assert media.as_dict()["title"] == "Clips (321)"
    assert (
        media.as_dict()["media_content_id"]
        == f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/event-search/clips//////"
    )

    assert {
        **DRILLDOWN_BASE,
        "title": "Yesterday (53)",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.yesterday/1622678400/1622764800///"
        ),
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "title": "Today (103)",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.today/1622764800////"
        ),
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "title": "This Month (210)",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month/1622505600////"
        ),
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.last_month/1619827200/1622505600///"
        ),
        "title": "Last Month (55)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_year/1609459200////"
        ),
        "title": "This Year",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door///front_door//"
        ),
        "title": "Front Door (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.person////person/"
        ),
        "title": "Person (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.steps/////steps"
        ),
        "title": "Steps (52)",
    } in media.as_dict()["children"]


async def test_async_browse_media_clip_search_drilldown(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test drilling down through clips."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    with patch("custom_components.frigate.media_source.dt.datetime", new=TODAY):
        media = await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/event-search/clips/.front_door/////"
            ),
        )

    assert len(media.as_dict()["children"]) == 58

    assert {
        "media_class": "video",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event/clips/front_door/1623454583.525913-y14xk9"
        ),
        "can_play": True,
        "can_expand": False,
        "children_media_class": None,
        "thumbnail": f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/thumbnail/1623454583.525913-y14xk9",
        "title": "2021-06-11 23:36:23 [8s, Person 72%]",
        "frigate": {
            "event": {
                "camera": "front_door",
                "end_time": 1623454592.311938,
                "false_positive": False,
                "has_clip": True,
                "has_snapshot": False,
                "id": "1623454583.525913-y14xk9",
                "label": "person",
                "start_time": 1623454583.525913,
                "data": {"top_score": 0.720703125},
                "zones": [],
            }
        },
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.this_month/1622505600////"
        ),
        "title": "This Month (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.last_month/1619827200/1622505600///"
        ),
        "title": "Last Month (55)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.this_year/1609459200////"
        ),
        "title": "This Year",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.front_door///front_door//"
        ),
        "title": "Front Door (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.person////person/"
        ),
        "title": "Person (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.front_door.steps/////steps"
        ),
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into this month.
    with patch("custom_components.frigate.media_source.dt.datetime", new=TODAY):
        media = await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/event-search/clips/.this_month/1622530800////"
            ),
        )

    # There are 50 events, and 5 drilldowns.
    assert len(media.as_dict()["children"]) == 55

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-02/1622592000/1622678400///"
        ),
        "title": "June 02 (54)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-03/1622678400/1622764800///"
        ),
        "title": "June 03 (53)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.front_door/1622530800//front_door//"
        ),
        "title": "Front Door (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.person/1622530800///person/"
        ),
        "title": "Person (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.steps/1622530800////steps"
        ),
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into this day.
    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04/1622764800/1622851200///"
        ),
    )

    # There are 50 events, and 3 drilldowns.
    assert len(media.as_dict()["children"]) == 53

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door"
            "/1622764800/1622851200/front_door//"
        ),
        "title": "Front Door (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.person/1622764800/1622851200"
            "//person/"
        ),
        "title": "Person (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.steps/1622764800/1622851200"
            "///steps"
        ),
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into the "Front Door"
    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door"
            "/1622764800/1622851200/front_door//"
        ),
    )

    # There are 50 events, and 2 drilldowns.
    assert len(media.as_dict()["children"]) == 52

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door.person"
            "/1622764800/1622851200/front_door/person/"
        ),
        "title": "Person (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door.steps"
            "/1622764800/1622851200/front_door//steps"
        ),
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into "Person"
    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door.person"
            "/1622764800/1622851200/front_door/person/"
        ),
    )

    assert len(media.as_dict()["children"]) == 51

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/.this_month.2021-06-04.front_door.person.all"
            "/1622764800/1622851200/front_door/person/"
        ),
        "title": "All (103)",
    } in media.as_dict()["children"]


async def test_async_browse_media_clip_search_multi_month_drilldown(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test a multi-month drilldown."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    before = int(
        datetime.datetime(2021, 3, 31, tzinfo=datetime.timezone.utc).timestamp()
    )
    after = int(datetime.datetime(2021, 2, 1, tzinfo=datetime.timezone.utc).timestamp())

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            f"/event-search/clips/Title/{after}/{before}///"
        ),
    )

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/Title.2021-02/1612137600/1614556800///"
        ),
        "title": "February (0)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips/Title.2021-03/1614816000/1617494400///"
        ),
        "title": "March (0)",
    } in media.as_dict()["children"]


async def test_async_resolve_media(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test successful resolve media."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    # Test resolving a clip.
    media = await media_source.async_resolve_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/event/clips/camera/CLIP-FOO",
    )
    assert media == PlayMedia(
        url=f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/event/CLIP-FOO/index.m3u8",
        mime_type="application/x-mpegURL",
    )

    # Test resolving a recording.
    media = await media_source.async_resolve_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/front_door/2021-05-30/15/46.08.mp4"
        ),
    )

    # Convert from HA local timezone to UTC.
    info = await system_info.async_get_system_info(hass)
    date = datetime.datetime(2021, 5, 30, 15, 46, 8, 0, datetime.timezone.utc) - (
        datetime.datetime.now(pytz.timezone(info.get("timezone", "utc"))).utcoffset()
        or datetime.timedelta()
    )

    assert media == PlayMedia(
        url=(
            f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/"
            + date.strftime("%Y-%m/%d/%H")
            + "/front_door/utc/index.m3u8"
        ),
        mime_type="application/x-mpegURL",
    )

    # Test resolving a snapshot.
    media = await media_source.async_resolve_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event/snapshots/camera/event_id"
        ),
    )
    assert media == PlayMedia(
        url=f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/snapshot/event_id",
        mime_type="image/jpg",
    )

    with pytest.raises(Unresolvable):
        media = await media_source.async_resolve_media(
            hass, f"{const.URI_SCHEME}{DOMAIN}/UNKNOWN"
        )


async def test_async_browse_media_recordings_root(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test recordings root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings",
    )

    assert media.as_dict() == {
        "title": "Recordings",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/recordings///"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/front_door//"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "Front Door",
            }
        ],
    }

    frigate_client.async_get_recordings_summary = AsyncMock(
        return_value=[
            {
                "day": "2022-12-31",
                "events": 11,
                "hours": [
                    {
                        "duration": 3582,
                        "events": 2,
                        "hour": "01",
                        "motion": 133116366,
                        "objects": 832,
                    },
                    {
                        "duration": 3537,
                        "events": 3,
                        "hour": "00",
                        "motion": 146836625,
                        "objects": 1118,
                    },
                ],
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door//",
    )

    assert media.as_dict() == {
        "title": "Recordings",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door//"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/front_door/2022-12-31/"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "2022-12-31",
            }
        ],
    }

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/front_door/2022-12-31/00"
        ),
    )

    assert media.as_dict() == {
        "title": "Recordings",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/front_door/2022-12-31/00"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "movie",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/front_door/2022-12-31/01"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "01:00",
            },
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "movie",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/front_door/2022-12-31/00"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "00:00",
            },
        ],
    }

    # Verify an inappropriate identifier will result in a MediaSourceError.
    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/recordings/2021-06/04/NOT_AN_HOUR/"
            ),
        )

    # Ensure API error results in MediaSourceError
    frigate_client.async_get_recordings_summary = AsyncMock(
        side_effect=FrigateApiClientError()
    )
    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/recordings/front_door/2022-12-31/00"
            ),
        )

    # Ensure a syntactically correct, but semantically incorrect path will
    # result in a MediaSourceError (there is no 24th hour).
    with pytest.raises(MediaSourceError):
        frigate_client.async_get_recordings_summary = AsyncMock(
            return_value=[
                {
                    "day": "2022-12-31",
                    "events": 11,
                    "hours": [
                        {
                            "duration": 3582,
                            "events": 2,
                            "hour": "24",
                            "motion": 133116366,
                            "objects": 832,
                        },
                    ],
                },
            ]
        )
        await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/recordings/front_door/2022-12-31/"
            ),
        )

    # Ensure a syntactically correct, but semantically incorrect path will
    # result in a MediaSourceError (there is no 29th February in 2022).
    with pytest.raises(MediaSourceError):
        frigate_client.async_get_recordings_summary = AsyncMock(
            return_value=[
                {
                    "day": "2022-2-29",
                    "events": 11,
                    "hours": [
                        {
                            "duration": 3582,
                            "events": 2,
                            "hour": "01",
                            "motion": 133116366,
                            "objects": 832,
                        },
                    ],
                },
            ]
        )
        await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/recordings/front_door//"
            ),
        )


async def test_async_browse_media_async_get_event_summary_error(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test API error behavior."""
    frigate_client.async_get_event_summary = AsyncMock(
        side_effect=FrigateApiClientError
    )

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips",
        )


async def test_async_browse_media_async_get_events_error(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test API error behavior."""
    frigate_client.async_get_events = AsyncMock(side_effect=FrigateApiClientError)

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/clips",
        )


async def test_identifier() -> None:
    """Test base identifier."""
    identifier = Identifier("foo")
    assert identifier.frigate_instance_id == "foo"

    # Base identifiers do not have a type and are not intended to be used
    # directly.
    with pytest.raises(NotImplementedError):
        identifier.get_identifier_type()

    # Base identifiers do not have a media properties.
    with pytest.raises(NotImplementedError):
        identifier.mime_type

    with pytest.raises(NotImplementedError):
        identifier.media_type

    with pytest.raises(NotImplementedError):
        identifier.media_class


async def test_event_search_identifier() -> None:
    """Test event search identifier."""
    identifier_in = (
        f"{TEST_FRIGATE_INSTANCE_ID}/event-search"
        "/clips/.this_month.2021-06-04.front_door.person"
        "/1622764800/1622851200/front_door/person/zone"
    )
    identifier = Identifier.from_str(identifier_in)

    assert identifier
    assert isinstance(identifier, EventSearchIdentifier)
    assert identifier.frigate_instance_id == TEST_FRIGATE_INSTANCE_ID
    assert identifier.name == ".this_month.2021-06-04.front_door.person"
    assert identifier.frigate_media_type == FrigateMediaType("clips")
    assert identifier.after == 1622764800
    assert identifier.before == 1622851200
    assert identifier.camera == "front_door"
    assert identifier.label == "person"
    assert identifier.zone == "zone"
    assert str(identifier) == identifier_in
    assert not identifier.is_root()

    # Event searches have no equivalent Frigate server path (searches result in
    # EventIdentifiers, that do have a Frigate server path).
    with pytest.raises(NotImplementedError):
        identifier.get_integration_proxy_path("utc")

    # Invalid "after" time.
    assert (
        EventSearchIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/event-search/clips"
            "/.this_month.2021-06-04.front_door.person/NOT_AN_INT/1622851200"
            "/front_door/person/zone"
        )
        is None
    )

    # Not a clips identifier.
    assert (
        EventSearchIdentifier.from_str(
            "{TEST_FRIGATE_INSTANCE_ID}/event-search/something/something"
        )
        is None
    )

    assert EventSearchIdentifier(
        TEST_FRIGATE_INSTANCE_ID, FrigateMediaType.CLIPS
    ).is_root()


async def test_recordings_identifier() -> None:
    """Test recordings identifier."""
    identifier_in = f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/2021-06-04/15"
    identifier = Identifier.from_str(identifier_in)

    assert identifier
    assert isinstance(identifier, RecordingIdentifier)
    assert identifier.frigate_instance_id == TEST_FRIGATE_INSTANCE_ID
    assert identifier.camera == "front_door"
    assert identifier.year_month_day == "2021-06-04"
    assert identifier.hour == 15
    assert str(identifier) == identifier_in

    # Test acceptable boundary conditions.
    for path in ("0001-1-1/0", "9000-12-31/23"):
        assert (
            Identifier.from_str(
                f"{TEST_FRIGATE_INSTANCE_ID}/recordings/cam/{path}/media"
            )
            is not None
        )

    # Year is not an int.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/NOT_AN_INT-06-04/15"
        )
        is None
    )

    # No 13th month.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/2021-13-04/15"
        )
        is None
    )

    # No 32nd day.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/2021-12-32/15"
        )
        is None
    )

    # No 25th hour.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/2021-12-28/25"
        )
        is None
    )

    # Not a recording identifier.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/event-search/something/something"
        )
        is None
    )

    # A missing element (no year-month-day) in the identifier, so no path will be possible
    # beyond the path to the day.
    with pytest.raises(MediaSourceError):
        identifier_in = f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door//15"
        identifier = RecordingIdentifier.from_str(identifier_in)
        assert identifier is not None
        identifier.get_integration_proxy_path("utc")

    # Verify a zero hour:
    # https://github.com/blakeblackshear/frigate-hass-integration/issues/126
    identifier = RecordingIdentifier.from_str(
        f"{TEST_FRIGATE_INSTANCE_ID}/recordings/front_door/2021-06-4/00"
    )
    assert identifier


async def test_event_identifier() -> None:
    """Test event identifier."""
    identifier_in = f"{TEST_FRIGATE_INSTANCE_ID}/event/clips/camera/something"
    identifier = Identifier.from_str(identifier_in)

    assert identifier
    assert isinstance(identifier, EventIdentifier)
    assert identifier.frigate_instance_id == TEST_FRIGATE_INSTANCE_ID
    assert identifier.frigate_media_type == FrigateMediaType.CLIPS
    assert identifier.camera == "camera"
    assert identifier.id == "something"
    assert identifier.mime_type == "application/x-mpegURL"

    assert not Identifier.from_str(f"{TEST_FRIGATE_INSTANCE_ID}/event/clips/something")

    assert not Identifier.from_str(
        f"{TEST_FRIGATE_INSTANCE_ID}/event/NOT_VALID/camera/something"
    )


async def test_get_client_non_existent(hass: HomeAssistant) -> None:
    """Test getting a FrigateApiClient for a non-existent config entry id."""

    await setup_mock_frigate_config_entry(hass)
    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/NOT_A_REAL_CONFIG_ENTRY_ID/event-search/clips",
        )

    # For code coverage and completeness check that _get_client(...) will raise
    # on an invalid instance_id since it is used inline in many places. There's
    # no public way to trigger this since there'll always be an earlier call to
    # _is_allowed_as_media_source will always have caught this issue upstream.
    source = await async_get_media_source(hass)
    with pytest.raises(MediaSourceError):
        # pylint: disable=protected-access
        source._get_client(
            Identifier.from_str(
                "NOT_A_REAL_CONFIG_ENTRY_ID/event-search"
                "/clips/.this_month.2021-06-04.front_door.person"
                "/1622764800/1622851200/front_door/person/zone"
            )
        )


async def test_backwards_compatability_identifier_without_frigate_instance_id(
    hass: HomeAssistant,
) -> None:
    """Test identifiers without an explicit instance id continue to work.

    If there is more than a single Frigate instance, these identifiers are
    expected to fail.
    """

    await setup_mock_frigate_config_entry(hass)

    for kind in ("event-search/clips", "event-search/snapshots", "recordings"):
        without_config_entry_id = await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{kind}",
        )
        with_config_entry_id = await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/{kind}",
        )
        assert without_config_entry_id.as_dict() == with_config_entry_id.as_dict()

    # Make a second Frigate instance -- no defaults allowed.
    create_mock_frigate_config_entry(hass, entry_id="another_id")

    for kind in ("event-search/clips", "event-search/snapshots", "recordings"):
        with pytest.raises(MediaSourceError):
            await media_source.async_browse_media(
                hass,
                f"{const.URI_SCHEME}{DOMAIN}/{kind}",
            )


async def test_snapshots(hass: HomeAssistant) -> None:
    """Test snapshots in media browser."""

    client = create_mock_frigate_client()
    client.async_get_event_summary = AsyncMock(
        return_value=[
            {
                "camera": "front_door",
                "count": 1,
                "day": "2021-06-04",
                "label": "person",
                "zones": [],
            }
        ]
    )
    client.async_get_events = AsyncMock(
        return_value=[
            {
                "camera": "front_door",
                "end_time": 1622764901.546445,
                "false_positive": False,
                "has_clip": True,
                "has_snapshot": True,
                "id": "1622764801.555377-55xy6j",
                "label": "person",
                "start_time": 1622764801,
                "data": {"top_score": 0.7265625},
                "zones": [],
            }
        ]
    )
    await setup_mock_frigate_config_entry(hass, client=client)

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/snapshots/.this_month.2021-06-04.front_door.person"
            "/1622764800/1622851200/front_door/person/"
        ),
    )

    assert len(media.as_dict()["children"]) == 1

    assert media.as_dict() == {
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/event-search"
            "/snapshots/.this_month.2021-06-04.front_door.person/1622764800"
            "/1622851200/front_door/person/"
        ),
        "title": "This Month > 2021-06-04 > Front Door > Person (1)",
        "media_class": "directory",
        "media_content_type": "image",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "image",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                "title": "2021-06-04 00:00:01 [100s, Person 72%]",
                "media_class": "image",
                "media_content_type": "image",
                "media_content_id": "media-source://frigate/frigate_client_id/event/snapshots/front_door/1622764801.555377-55xy6j",
                "can_play": False,
                "can_expand": False,
                "children_media_class": None,
                "thumbnail": f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/thumbnail/1622764801.555377-55xy6j",
                "frigate": {
                    "event": {
                        "camera": "front_door",
                        "end_time": 1622764901.546445,
                        "false_positive": False,
                        "has_clip": True,
                        "has_snapshot": True,
                        "id": "1622764801.555377-55xy6j",
                        "label": "person",
                        "start_time": 1622764801,
                        "data": {"top_score": 0.7265625},
                        "zones": [],
                    }
                },
            }
        ],
    }

    assert client.async_get_event_summary.call_args == call(
        has_snapshot=True, timezone="US/Pacific"
    )
    assert client.async_get_events.call_args == call(
        after=1622764800,
        before=1622851200,
        cameras=["front_door"],
        labels=["person"],
        sub_labels=None,
        zones=None,
        limit=50,
        has_snapshot=True,
    )


async def test_media_types() -> None:
    """Test FrigateMediaTypes."""
    snapshots = FrigateMediaType("snapshots")
    assert snapshots.mime_type == "image/jpg"
    assert snapshots.media_class == "image"
    assert snapshots.media_type == "image"
    assert snapshots.extension == "jpg"

    clips = FrigateMediaType("clips")
    assert clips.mime_type == "application/x-mpegURL"
    assert clips.media_class == "video"
    assert clips.media_type == "video"
    assert clips.extension == "m3u8"


async def test_in_progress_event(hass: HomeAssistant) -> None:
    """Verify in progress events are handled correctly."""
    client = create_mock_frigate_client()
    client.async_get_event_summary = AsyncMock(
        return_value=[
            {
                "camera": "front_door",
                "count": 1,
                "day": "2021-06-04",
                "label": "person",
                "zones": [],
            }
        ]
    )
    client.async_get_events = AsyncMock(
        return_value=[
            {
                "camera": "front_door",
                # Event has not yet ended:
                "end_time": None,
                "false_positive": False,
                "has_clip": True,
                "has_snapshot": True,
                "id": "1622764820.555377-55xy6j",
                "label": "person",
                # This is 10s before the value of TODAY:
                "start_time": 1622764820.0,
                "data": {"top_score": 0.7265625},
                "zones": [],
            }
        ]
    )
    await setup_mock_frigate_config_entry(hass, client=client)

    with patch("custom_components.frigate.media_source.dt.datetime", new=TODAY):
        media = await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/event-search/snapshots/.this_month.2021-06-04.front_door.person"
                "/1622764800/1622851200/front_door/person/"
            ),
        )

    assert len(media.as_dict()["children"]) == 1

    assert media.as_dict() == {
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/event-search"
            "/snapshots/.this_month.2021-06-04.front_door.person/1622764800"
            "/1622851200/front_door/person/"
        ),
        "title": "This Month > 2021-06-04 > Front Door > Person (1)",
        "media_class": "directory",
        "media_content_type": "image",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "image",
        "thumbnail": None,
        "not_shown": 0,
        "children": [
            {
                # Duration will be shown as 10s, since 10s has elapsed since
                # this event started.
                "title": "2021-06-04 00:00:20 [10s, Person 72%]",
                "media_class": "image",
                "media_content_type": "image",
                "media_content_id": "media-source://frigate/frigate_client_id/event/snapshots/front_door/1622764820.555377-55xy6j",
                "can_play": False,
                "can_expand": False,
                "children_media_class": None,
                "thumbnail": f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/thumbnail/1622764820.555377-55xy6j",
                "frigate": {
                    "event": {
                        "camera": "front_door",
                        "end_time": None,
                        "false_positive": False,
                        "has_clip": True,
                        "has_snapshot": True,
                        "id": "1622764820.555377-55xy6j",
                        "label": "person",
                        "start_time": 1622764820.0,
                        "data": {"top_score": 0.7265625},
                        "zones": [],
                    }
                },
            }
        ],
    }


async def test_bad_event(hass: HomeAssistant) -> None:
    """Verify malformed events are handled correctly."""
    client = create_mock_frigate_client()
    client.async_get_events = AsyncMock(
        return_value=[
            {
                "camera": "front_door",
                "end_time": None,
                # Events without a start_time are skipped.
                "start_time": None,
                "false_positive": False,
                "has_clip": True,
                "has_snapshot": True,
                "id": "1622764820.555377-55xy6j",
                "label": "person",
                "data": {"top_score": 0.7265625},
                "zones": [],
            }
        ]
    )
    await setup_mock_frigate_config_entry(hass, client=client)

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event-search/snapshots/.this_month.2021-06-04.front_door.person"
            "/1622764800/1622851200/front_door/person/"
        ),
    )

    assert len(media.as_dict()["children"]) == 0
