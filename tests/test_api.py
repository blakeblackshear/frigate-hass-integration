"""Test the frigate API client."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import datetime
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
import pytest

from custom_components.frigate.api import FrigateApiClient, FrigateApiClientError

from . import TEST_SERVER_VERSION, start_frigate_server

_LOGGER = logging.getLogger(__name__)

# ==============================================================================
# Please do not add HomeAssistant specific imports/functionality to this test,
# so that this library can be optionally moved to a different repo at a later
# date.
# ==============================================================================


@pytest.fixture
async def aiohttp_session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """Test fixture for aiohttp.ClientSerssion."""
    async with aiohttp.ClientSession() as session:
        yield session


def _assert_request_params(
    request: web.Request, expected_params: dict[str, str]
) -> None:
    """Assert expected parameters."""
    for key, value in expected_params.items():
        assert request.query.get(key) == value


async def test_async_get_stats(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_config."""
    stats_in = {"detection_fps": 8.1}
    stats_handler = AsyncMock(return_value=web.json_response(stats_in))

    server = await start_frigate_server(
        aiohttp_server, [web.get("/api/stats", stats_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert stats_in == await frigate_client.async_get_stats()


async def test_async_get_events(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_events."""
    events_in = [
        {
            "camera": "front_door",
            "end_time": 1623643757.837382,
            "false_positive": False,
            "has_clip": True,
            "has_snapshot": False,
            "id": "1623643750.569992-64ji22",
            "label": "person",
            "start_time": 1623643750.569992,
            "thumbnail": "thumbnail",
            "data": {"top_score": 0.70703125},
            "zones": [],
        }
    ]

    async def events_handler(request: web.Request) -> web.Response:
        """Events handler."""
        _assert_request_params(
            request,
            {
                "cameras": "test_camera1,test_camera2",
                "labels": "test_label1,test_label2",
                "sub_labels": "test_sub_label1,test_sub_label2",
                "zones": "test_zone1,test_zone2",
                "after": "1",
                "before": "2",
                "limit": "3",
                "has_clip": "1",
            },
        )
        return web.json_response(events_in)

    server = await start_frigate_server(
        aiohttp_server, [web.get("/api/events", events_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert events_in == await frigate_client.async_get_events(
        cameras=["test_camera1", "test_camera2"],
        labels=["test_label1", "test_label2"],
        sub_labels=["test_sub_label1", "test_sub_label2"],
        zones=["test_zone1", "test_zone2"],
        after=1,
        before=2,
        limit=3,
        has_clip=True,
    )


async def test_async_get_event_summary_clips(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_event_summary."""
    events_summary_in = [
        {
            "camera": "front_door",
            "count": 76,
            "day": "2021-06-12",
            "label": "person",
            "zones": [],
        },
    ]
    expected_params = [
        {"has_clip": "1"},
        {"has_snapshot": "1"},
    ]

    async def events_summary_handler(request: web.Request) -> web.Response:
        """Events summary handler."""
        _assert_request_params(request, expected_params.pop(0))
        return web.json_response(events_summary_in)

    server = await start_frigate_server(
        aiohttp_server, [web.get("/api/events/summary", events_summary_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)

    assert events_summary_in == await frigate_client.async_get_event_summary(
        has_clip=True,
    )
    assert events_summary_in == await frigate_client.async_get_event_summary(
        has_snapshot=True,
    )


async def test_async_get_config(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_event_summary."""
    config_in = {"cameras": {"front_door": {"camera_config": "goes here"}}}
    config_handler = AsyncMock(return_value=web.json_response(config_in))

    server = await start_frigate_server(
        aiohttp_server, [web.get("/api/config", config_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert config_in == await frigate_client.async_get_config()


async def test_async_get_path(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_path."""
    recordings_in = [
        {
            "name": "2021-05",
            "type": "directory",
            "mtime": "Sun, 04 June 2021 22:47:14 GMT",
        }
    ]

    recordings_handler = AsyncMock(return_value=web.json_response(recordings_in))

    server = await start_frigate_server(
        aiohttp_server, [web.get("/recordings/moo", recordings_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert recordings_in == await frigate_client.async_get_path("recordings/moo")


async def test_api_wrapper_methods(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test the general api_wrapper."""

    get_handler = AsyncMock(return_value=web.json_response({"method": "GET"}))
    put_handler = AsyncMock(return_value=web.json_response({"method": "PUT"}))
    patch_handler = AsyncMock(return_value=web.json_response({"method": "PATCH"}))
    post_handler = AsyncMock(return_value=web.json_response({"method": "POST"}))

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.get("/get", get_handler),
            web.put("/put", put_handler),
            web.patch("/patch", patch_handler),
            web.post("/post", post_handler),
        ],
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)

    assert await frigate_client.api_wrapper(
        method="get", url=server.make_url("/get")
    ) == {"method": "GET"}
    assert get_handler.called

    await frigate_client.api_wrapper(method="put", url=server.make_url("/put"))
    assert put_handler.called

    await frigate_client.api_wrapper(method="patch", url=server.make_url("/patch"))
    assert patch_handler.called

    await frigate_client.api_wrapper(method="post", url=server.make_url("/post"))
    assert post_handler.called


async def test_api_wrapper_exceptions(
    caplog: Any, aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test the general api_wrapper."""

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.get("/get", AsyncMock(return_value=web.json_response({}))),
        ],
    )
    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)

    with patch.object(aiohttp_session, "get", side_effect=asyncio.TimeoutError):
        with pytest.raises(FrigateApiClientError):
            await frigate_client.api_wrapper(method="get", url=server.make_url("/get"))
            assert "Timeout error" in caplog.text
    caplog.clear()

    with patch.object(aiohttp_session, "get", side_effect=TypeError):
        with pytest.raises(FrigateApiClientError):
            await frigate_client.api_wrapper(method="get", url=server.make_url("/get"))
            assert "Error parsing information" in caplog.text
    caplog.clear()

    with patch.object(aiohttp_session, "get", side_effect=aiohttp.ClientError):
        with pytest.raises(FrigateApiClientError):
            await frigate_client.api_wrapper(method="get", url=server.make_url("/get"))
            assert "Error fetching information" in caplog.text
    caplog.clear()


async def test_async_get_version(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_version."""

    async def version_handler(request: web.Request) -> web.Response:
        """Events summary handler."""
        return web.Response(text=TEST_SERVER_VERSION)

    server = await start_frigate_server(
        aiohttp_server, [web.get("/api/version", version_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert await frigate_client.async_get_version() == TEST_SERVER_VERSION


async def test_async_retain(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_retain."""

    post_success = {"success": True, "message": "Post success"}
    post_handler = AsyncMock(return_value=web.json_response(post_success))

    delete_success = {"success": True, "message": "Delete success"}
    delete_handler = AsyncMock(return_value=web.json_response(delete_success))

    event_id = "1656282822.206673-bovnfg"
    server = await start_frigate_server(
        aiohttp_server,
        [
            web.post(f"/api/events/{event_id}/retain", post_handler),
            web.delete(f"/api/events/{event_id}/retain", delete_handler),
        ],
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert await frigate_client.async_retain(event_id, True) == post_success
    assert post_handler.called
    assert not delete_handler.called

    assert await frigate_client.async_retain(event_id, False) == delete_success
    assert delete_handler.called


async def test_async_export_recording(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_export_recording."""

    post_success = {"success": True, "message": "Post success"}
    post_handler = AsyncMock(return_value=web.json_response(post_success))

    playback_factor = "Realtime"
    start_time = datetime.datetime.strptime(
        "2023-09-23 13:33:44", "%Y-%m-%d %H:%M:%S"
    ).timestamp()
    end_time = datetime.datetime.strptime(
        "2023-09-23 18:11:22", "%Y-%m-%d %H:%M:%S"
    ).timestamp()
    server = await start_frigate_server(
        aiohttp_server,
        [
            web.post(
                f"/api/export/front_door/start/{start_time}/end/{end_time}",
                post_handler,
            ),
        ],
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert (
        await frigate_client.async_export_recording(
            "front_door", playback_factor, start_time, end_time
        )
        == post_success
    )
    assert post_handler.called


async def test_async_get_recordings_summary(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_recordings_summary."""

    summary_success = [{"summary": "goes_here"}]
    summary_handler = AsyncMock(return_value=web.json_response(summary_success))
    camera = "front_door"

    server = await start_frigate_server(
        aiohttp_server, [web.get(f"/api/{camera}/recordings/summary", summary_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert (
        await frigate_client.async_get_recordings_summary(camera, "utc")
        == summary_success
    )
    assert summary_handler.called


async def test_async_get_recordings(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_recordings."""

    recordings_success = {"recordings": "goes_here"}
    camera = "front_door"
    after = 1
    before = 2

    async def recordings_handler(request: web.Request) -> web.Response:
        """Events handler."""
        _assert_request_params(
            request,
            {
                "before": str(before),
                "after": str(after),
            },
        )
        return web.json_response(recordings_success)

    server = await start_frigate_server(
        aiohttp_server, [web.get(f"/api/{camera}/recordings", recordings_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert (
        await frigate_client.async_get_recordings(camera, after, before)
        == recordings_success
    )


async def test_async_get_ptz_info(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_get_ptz_info."""

    camera = "master_bedroom"
    summary_success = [
        {
            "features": ["pt", "zoom", "pt-r", "zoom-r"],
            "name": camera,
            "presets": [
                "preset01",
                "preset02",
            ],
        }
    ]
    summary_handler = AsyncMock(return_value=web.json_response(summary_success))

    server = await start_frigate_server(
        aiohttp_server, [web.get(f"/api/{camera}/ptz/info", summary_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert await frigate_client.async_get_ptz_info(camera) == summary_success
    assert summary_handler.called
