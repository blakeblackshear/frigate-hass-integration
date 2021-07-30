"""Test the frigate API client."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import logging
from typing import Any
from unittest.mock import Mock, patch

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
    stats_handler = Mock(return_value=web.json_response(stats_in))

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
            "top_score": 0.70703125,
            "zones": [],
        }
    ]

    async def events_handler(request: web.Request) -> web.Response:
        """Events handler."""
        _assert_request_params(
            request,
            {
                "camera": "test_camera",
                "label": "test_label",
                "zone": "test_zone",
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
        camera="test_camera",
        label="test_label",
        zone="test_zone",
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
    config_handler = Mock(return_value=web.json_response(config_in))

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

    recordings_handler = Mock(return_value=web.json_response(recordings_in))

    server = await start_frigate_server(
        aiohttp_server, [web.get("/recordings/moo/", recordings_handler)]
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert recordings_in == await frigate_client.async_get_path("recordings/moo")


async def test_api_wrapper_methods(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test the general api_wrapper."""

    get_handler = Mock(return_value=web.json_response({"method": "GET"}))
    put_handler = Mock(return_value=web.json_response({"method": "PUT"}))
    patch_handler = Mock(return_value=web.json_response({"method": "PATCH"}))
    post_handler = Mock(return_value=web.json_response({"method": "POST"}))

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
            web.get("/get", Mock(return_value=web.json_response({}))),
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
