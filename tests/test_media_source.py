"""Test Frigate Media Source."""
import datetime
import json
import logging
import os
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.frigate.const import DOMAIN
from custom_components.frigate.media_source import CLIPS_ROOT, RECORDINGS_ROOT
from homeassistant.components import media_source
from homeassistant.components.media_source import const
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.core import HomeAssistant

from . import create_mock_frigate_client, setup_mock_frigate_config_entry

_LOGGER = logging.getLogger(__name__)


def _get_fixed_datetime():
    """Get a fixed-in-time datetime."""
    datetime_today = Mock(wraps=datetime.datetime)
    datetime_today.now = Mock(
        return_value=datetime.datetime(2021, 6, 4, 0, 0, tzinfo=datetime.timezone.utc)
    )
    return datetime_today


TODAY = _get_fixed_datetime()
DRILLDOWN_BASE = {
    "media_class": "directory",
    "media_content_type": "video",
    "can_play": False,
    "can_expand": True,
    "children_media_class": "video",
    "thumbnail": None,
}
EVENTS_FIXTURE_FILE = "events_front_door.json"


@pytest.fixture
def frigate_client() -> AsyncMock:
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

    await setup_mock_frigate_config_entry(hass)
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
                "title": "Clips",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": "media-source://frigate/clips//////",
                "can_play": False,
                "can_expand": True,
                "children_media_class": "video",
                "thumbnail": None,
            },
            {
                "title": "Recordings",
                "media_class": "directory",
                "media_content_type": "video",
                "media_content_id": "media-source://frigate/recordings////",
                "can_play": False,
                "can_expand": True,
                "children_media_class": "video",
                "thumbnail": None,
            },
        ],
    }


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_clips_root(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test browsing the media clips root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)
    media = await media_source.async_browse_media(
        hass, f"{const.URI_SCHEME}{DOMAIN}/{CLIPS_ROOT}"
    )

    assert len(media.as_dict()["children"]) == 58
    assert media.as_dict()["title"] == "Clips (321)"
    assert media.as_dict()["media_content_id"] == "media-source://frigate/clips//////"

    assert {
        **DRILLDOWN_BASE,
        "title": "Yesterday (53)",
        "media_content_id": "media-source://frigate/clips/.yesterday/1622678400/1622764800///",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "title": "Today (103)",
        "media_content_id": "media-source://frigate/clips/.today/1622764800////",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "title": "This Month (210)",
        "media_content_id": "media-source://frigate/clips/.this_month/1622505600////",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.last_month/1619827200/1622505600///",
        "title": "Last Month (55)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_year/1609459200////",
        "title": "This Year",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door///front_door//",
        "title": "Front Door (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.person////person/",
        "title": "Person (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.steps/////steps",
        "title": "Steps (52)",
    } in media.as_dict()["children"]


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_clips_drilldown(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test drilling down through clips."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    media = await media_source.async_browse_media(
        hass, f"{const.URI_SCHEME}{DOMAIN}/clips/.front_door/////"
    )

    assert len(media.as_dict()["children"]) == 58
    assert {
        "media_class": "video",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/clips/front_door-1623454583.525913-y14xk9.mp4",
        "can_play": True,
        "can_expand": False,
        "children_media_class": None,
        "thumbnail": "data:image/jpeg;base64,thumbnail",
        "title": "2021-06-11 23:36:23 [8s, Person 72%]",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.this_month/1622505600////",
        "title": "This Month (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.last_month/1619827200/1622505600///",
        "title": "Last Month (55)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.this_year/1609459200////",
        "title": "This Year",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.front_door///front_door//",
        "title": "Front Door (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.person////person/",
        "title": "Person (321)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.front_door.steps/////steps",
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into this month.
    media = await media_source.async_browse_media(
        hass, f"{const.URI_SCHEME}{DOMAIN}/clips/.this_month/1622530800////"
    )

    # There are 50 events, and 5 drilldowns.
    assert len(media.as_dict()["children"]) == 55

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-02/1622592000/1622678400///",
        "title": "June 02 (54)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-03/1622678400/1622764800///",
        "title": "June 03 (53)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.front_door/1622530800//front_door//",
        "title": "Front Door (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.person/1622530800///person/",
        "title": "Person (210)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.steps/1622530800////steps",
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into this day.
    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/clips/.this_month.2021-06-04/1622764800/1622851200///",
    )

    # There are 50 events, and 3 drilldowns.
    assert len(media.as_dict()["children"]) == 53

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.front_door/1622764800/1622851200/front_door//",
        "title": "Front Door (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.person/1622764800/1622851200//person/",
        "title": "Person (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.steps/1622764800/1622851200///steps",
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into the "Front Door"
    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/clips/.this_month.2021-06-04.front_door/1622764800/1622851200/front_door//",
    )

    # There are 50 events, and 2 drilldowns.
    assert len(media.as_dict()["children"]) == 52

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.front_door.person/1622764800/1622851200/front_door/person/",
        "title": "Person (103)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.front_door.steps/1622764800/1622851200/front_door//steps",
        "title": "Steps (52)",
    } in media.as_dict()["children"]

    # Drill down into "Person"
    media = await media_source.async_browse_media(
        hass,
        f"{const.URI_SCHEME}{DOMAIN}/clips/.this_month.2021-06-04.front_door.person/1622764800/1622851200/front_door/person/",
    )

    assert len(media.as_dict()["children"]) == 51

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/.this_month.2021-06-04.front_door.person.all/1622764800/1622851200/front_door/person/",
        "title": "All (103)",
    } in media.as_dict()["children"]


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_clips_multi_month_drilldown(
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
        f"{const.URI_SCHEME}{DOMAIN}/clips/Title/{after}/{before}///",
    )

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/Title.2021-02/1612137600/1614556800///",
        "title": "February (0)",
    } in media.as_dict()["children"]

    assert {
        **DRILLDOWN_BASE,
        "media_content_id": "media-source://frigate/clips/Title.2021-03/1614816000/1617494400///",
        "title": "March (0)",
    } in media.as_dict()["children"]


async def test_async_resolve_media_success(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test successful resolve media."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)
    media = await media_source.async_resolve_media(
        hass, f"{const.URI_SCHEME}{DOMAIN}/WHATEVER"
    )
    assert media == PlayMedia(url="/api/frigate/WHATEVER", mime_type="video/mp4")


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_recordings_root(
    caplog: Any, frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test recordings root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    frigate_client.async_get_recordings_folder = AsyncMock(
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
        hass, f"{const.URI_SCHEME}{DOMAIN}/{RECORDINGS_ROOT}"
    )

    assert media.as_dict() == {
        "title": "Recordings",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/recordings////",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "video",
                "media_class": "directory",
                "media_content_id": "media-source://frigate/recordings/2021-06///",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "June 2021",
            }
        ],
    }

    frigate_client.async_get_recordings_folder = AsyncMock(
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
        hass, f"{const.URI_SCHEME}{DOMAIN}/recordings/2021-06///"
    )

    assert media.as_dict() == {
        "title": "June 2021",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/recordings/2021-06///",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "video",
                "media_class": "directory",
                "media_content_id": "media-source://frigate/recordings/2021-06/04//",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "June 04",
            }
        ],
    }
    # There's a bogus value for an hour, that should be skipped.
    assert "Skipping non-standard folder" in caplog.text

    frigate_client.async_get_recordings_folder = AsyncMock(
        return_value=[
            {
                "name": "15",
                "type": "directory",
                "mtime": "Sun, 04 June 2021 22:47:14 GMT",
            },
        ]
    )

    media = await media_source.async_browse_media(
        hass, f"{const.URI_SCHEME}{DOMAIN}/recordings/2021-06/04//"
    )

    assert media.as_dict() == {
        "title": "June 04",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/recordings/2021-06/04//",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "video",
                "media_class": "directory",
                "media_content_id": "media-source://frigate/recordings/2021-06/04/15/",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:00:00",
            }
        ],
    }

    frigate_client.async_get_recordings_folder = AsyncMock(
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
        hass, f"{const.URI_SCHEME}{DOMAIN}/recordings/2021-06/04/15/"
    )

    assert media.as_dict() == {
        "title": "15:00:00",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/recordings/2021-06/04/15/",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "children": [
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "video",
                "media_class": "directory",
                "media_content_id": "media-source://frigate/recordings/2021-06/04/15/front_door",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "Front Door",
            },
            {
                "can_expand": True,
                "can_play": False,
                "children_media_class": "video",
                "media_class": "directory",
                "media_content_id": "media-source://frigate/recordings/2021-06/04/15/sitting_room",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "Sitting Room",
            },
        ],
    }


@patch("custom_components.frigate.media_source.dt.datetime", new=TODAY)
async def test_async_browse_media_recordings_for_camera(
    frigate_client: AsyncMock, hass: HomeAssistant
) -> None:
    """Test recordings root."""

    await setup_mock_frigate_config_entry(hass, client=frigate_client)

    frigate_client.async_get_recordings_folder = AsyncMock(
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
        f"{const.URI_SCHEME}{DOMAIN}/recordings/2021-06/04/15/front_door",
    )

    assert media.as_dict() == {
        "title": "Front Door",
        "media_class": "directory",
        "media_content_type": "video",
        "media_content_id": "media-source://frigate/recordings/2021-06/04/15/front_door",
        "can_play": False,
        "can_expand": True,
        "children_media_class": "video",
        "thumbnail": None,
        "children": [
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "video",
                "media_content_id": "media-source://frigate/recordings/2021-06/04/15/front_door/46.08.mp4",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:46:08",
            },
            {
                "can_expand": False,
                "can_play": True,
                "children_media_class": None,
                "media_class": "video",
                "media_content_id": "media-source://frigate/recordings/2021-06/04/15/front_door/47.08.mp4",
                "media_content_type": "video",
                "thumbnail": None,
                "title": "15:47:08",
            },
        ],
    }
