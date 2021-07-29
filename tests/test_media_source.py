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

from custom_components.frigate.api import FrigateApiClient, FrigateApiClientError
from custom_components.frigate.const import ATTR_CLIENT_ID, ATTR_MQTT, DOMAIN
from custom_components.frigate.media_source import (
    EventIdentifier,
    EventSearchIdentifier,
    FrigateMediaType,
    Identifier,
    RecordingIdentifier,
)
from homeassistant.components import media_source
from homeassistant.components.media_source import const
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

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
        return_value=datetime.datetime(2021, 6, 4, 0, 0, tzinfo=datetime.timezone.utc)
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


@pytest.fixture
def frigate_client() -> Generator[FrigateApiClient, None, None]:
    """Fixture that creates a frigate client."""

    def load_json(filename: str) -> Any:
        """Load json from a file."""
        path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)

    client = create_mock_frigate_client()
    client.async_get_events = AsyncMock(return_value=load_json(EVENTS_FIXTURE_FILE))
    yield client


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
                    "/recordings/////"
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
                    "media-source://frigate/another_client_id/recordings/////"
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


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_clip_search_root(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test browsing the media clips root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)
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


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_clip_search_drilldown(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test drilling down through clips."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

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
            "/event/clips/front_door-1623454583.525913-y14xk9.mp4"
        ),
        "can_play": True,
        "can_expand": False,
        "children_media_class": None,
        "thumbnail": "data:image/jpeg;base64,thumbnail",
        "title": "2021-06-11 23:36:23 [8s, Person 72%]",
    } in media.as_dict()["children"]

    _LOGGER.error(media.as_dict()["children"])
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


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
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
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/event/clips/CLIP-FOO",
    )
    assert media == PlayMedia(
        url=f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/clips/CLIP-FOO",
        mime_type="video/mp4",
    )

    # Test resolving a recording.
    media = await media_source.async_resolve_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-05/30/15/front_door/46.08.mp4"
        ),
    )
    assert media == PlayMedia(
        url=(
            f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-05/30/15"
            "/front_door/46.08.mp4"
        ),
        mime_type="video/mp4",
    )

    # Test resolving a snapshot.
    media = await media_source.async_resolve_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/event/snapshots/snapshot.jpg"
        ),
    )
    assert media == PlayMedia(
        url=f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/clips/snapshot.jpg",
        mime_type="image/jpg",
    )

    with pytest.raises(Unresolvable):
        media = await media_source.async_resolve_media(
            hass, f"{const.URI_SCHEME}{DOMAIN}/UNKNOWN"
        )


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_recordings_root(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test recordings root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "2021-06",
                "type": "directory",
                "mtime": "Sun, 30 June 2021 22:47:14 GMT",
            },
            {
                "name": "49.06.mp4",
                "type": "file",
                "mtime": "Sun, 30 June 2021 22:50:06 GMT",
                "size": 5168517,
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings",
    )

    assert media.as_dict() == {
        "title": "Recordings",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/recordings/////"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06////"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "June 2021",
            }
        ],
    }

    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "04",
                "type": "directory",
                "mtime": "Mon, 07 Jun 2021 02:33:16 GMT",
            },
            {
                "name": "NOT_AN_HOUR",
                "type": "directory",
                "mtime": "Mon, 07 Jun 2021 02:33:17 GMT",
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-06///",
    )

    assert media.as_dict() == {
        "title": "June 2021",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-06////"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04///"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "June 04",
            }
        ],
    }
    # There's a bogus value for an hour, that should be skipped.
    assert "Skipping non-standard folder" in caplog.text

    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "15",
                "type": "directory",
                "mtime": "Sun, 04 June 2021 22:47:14 GMT",
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-06/04//",
    )

    assert media.as_dict() == {
        "title": "June 04",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04///"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04/15//"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:00:00",
            }
        ],
    }

    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "front_door",
                "type": "directory",
                "mtime": "Sun, 30 June 2021 23:00:50 GMT",
            },
            {
                "name": "sitting_room",
                "type": "directory",
                "mtime": "Sun, 04 June 2021 23:00:40 GMT",
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04/15/"
        ),
    )

    assert media.as_dict() == {
        "title": "15:00:00",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04/15//"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04/15/front_door/"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "Front Door",
            },
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "directory",
                "media_class": "directory",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04/15/sitting_room/"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "Sitting Room",
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

    # Ensure a syntactically correct, but semantically incorrect path will
    # result in a MediaSourceError (there is no 29th February in 2021).
    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-02/29",
        )


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_recordings_for_camera(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test recordings for a camera."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "46.08.mp4",
                "type": "file",
                "mtime": "Sun, 04 June 2021 22:47:08 GMT",
                "size": 5480823,
            },
            {
                "name": "47.08.mp4",
                "type": "file",
                "mtime": "Sun, 04 June 2021 22:48:08 GMT",
                "size": 5372942,
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04/15/front_door"
        ),
    )

    assert media.as_dict() == {
        "title": "Front Door",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": (
            f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04/15/front_door/"
        ),
        "can_play": False,
        "can_expand": True,
        "children_media_class": "directory",
        "thumbnail": None,
        "children": [
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "movie",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04/15/front_door/46.08.mp4"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:46:08",
            },
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "movie",
                "media_content_id": (
                    f"media-source://frigate/{TEST_FRIGATE_INSTANCE_ID}"
                    "/recordings/2021-06/04/15/front_door/47.08.mp4"
                ),
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:47:08",
            },
        ],
    }

    # Verify an unexpected folder name will result in a suitable log message.
    frigate_client.async_get_path = AsyncMock(
        return_value=[
            {
                "name": "NOT_A_MINUTE.NOT_AN_HOUR.mp4",
                "type": "file",
                "mtime": "Sun, 04 June 2021 22:47:08 GMT",
                "size": 5480823,
            }
        ]
    )

    await media_source.async_browse_media(
        hass,
        (
            f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
            "/recordings/2021-06/04/15/front_door"
        ),
    )

    # There's a bogus value for an hour, that should be skipped.
    assert "Skipping non-standard recording name" in caplog.text


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
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


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
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


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_async_get_path_error(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test API error behavior."""
    frigate_client.async_get_path = AsyncMock(side_effect=FrigateApiClientError)

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass, f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}/recordings"
        )

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            (
                f"{const.URI_SCHEME}{DOMAIN}/{TEST_FRIGATE_INSTANCE_ID}"
                "/recordings/2021-06/04/15/front_door"
            ),
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
        identifier.get_frigate_server_path()

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
    identifier_in = (
        f"{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-06/04/15/front_door/media.mp4"
    )
    identifier = Identifier.from_str(identifier_in)

    assert identifier
    assert isinstance(identifier, RecordingIdentifier)
    assert identifier.frigate_instance_id == TEST_FRIGATE_INSTANCE_ID
    assert identifier.year_month == "2021-06"
    assert identifier.day == 4
    assert identifier.hour == 15
    assert identifier.recording_name == "media.mp4"
    assert str(identifier) == identifier_in

    with pytest.raises(ValueError):
        # The identifier is fully specified, there's no next available attribute.
        identifier.get_changes_to_set_next_empty("value")

    # Test acceptable boundary conditions.
    for path in ("0-1/1/0/0", "9000-12/31/23/59"):
        assert (
            Identifier.from_str(
                f"{TEST_FRIGATE_INSTANCE_ID}/recordings/{path}/cam/media"
            )
            is not None
        )

    # Year is not an int.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/NOT_AN_INT-06/04/15/front_door"
        )
        is None
    )

    # No 13th month.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-13/04/15/front_door"
        )
        is None
    )

    # No 32nd day.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-12/32/15/front_door"
        )
        is None
    )

    # No 25th hour.
    assert (
        RecordingIdentifier.from_str(
            f"{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-12/28/25/front_door"
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

    # A missing element (no hour) in the identifier, so no path will be possible
    # beyond the path to the day.
    identifier_in = f"{TEST_FRIGATE_INSTANCE_ID}/recordings/2021-06/04//front_door"
    identifier = RecordingIdentifier.from_str(identifier_in)
    assert identifier
    assert identifier.get_frigate_server_path() == "recordings/2021-06/04"


async def test_event_identifier() -> None:
    """Test event identifier."""
    identifier_in = f"{TEST_FRIGATE_INSTANCE_ID}/event/clips/something"
    identifier = Identifier.from_str(identifier_in)

    assert identifier
    assert isinstance(identifier, EventIdentifier)
    assert identifier.frigate_instance_id == TEST_FRIGATE_INSTANCE_ID
    assert identifier.frigate_media_type == FrigateMediaType.CLIPS
    assert identifier.name == "something"
    assert identifier.mime_type == "video/mp4"

    assert not Identifier.from_str(
        f"{TEST_FRIGATE_INSTANCE_ID}/event/NOT_A_THING/something"
    )


async def test_get_client_non_existent(hass: HomeAssistant) -> None:
    """Test getting a FrigateApiClient for a non-existent config entry id."""

    await setup_mock_frigate_config_entry(hass)
    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            hass,
            f"{const.URI_SCHEME}{DOMAIN}/NOT_A_REAL_CONFIG_ENTRY_ID/event-search/clips",
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
                "top_score": 0.7265625,
                "zones": [],
                "thumbnail": "thumbnail",
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
        "children": [
            {
                "title": "2021-06-04 00:00:01 [100s, Person 72%]",
                "media_class": "image",
                "media_content_type": "image",
                "media_content_id": "media-source://frigate/frigate_client_id/event/snapshots/front_door-1622764801.555377-55xy6j.jpg",
                "can_play": False,
                "can_expand": False,
                "children_media_class": None,
                "thumbnail": "data:image/jpeg;base64,thumbnail",
            }
        ],
    }

    assert client.async_get_event_summary.call_args == call(has_snapshot=True)
    assert client.async_get_events.call_args == call(
        after=1622764800,
        before=1622851200,
        camera="front_door",
        label="person",
        zone=None,
        limit=50,
        has_snapshot=True,
    )
