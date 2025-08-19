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
import jwt
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
async def aiohttp_session() -> AsyncGenerator[aiohttp.ClientSession]:
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
        aiohttp_server, [web.get("/recordings/moo/", recordings_handler)]
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


def get_test_token(expiration: datetime.timedelta = datetime.timedelta(hours=1)) -> str:
    return jwt.encode(
        {
            "sub": "test_user",
            "exp": (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
            ).timestamp(),
        },
        key="secret",
        algorithm="HS256",
    )


async def test_get_token_success(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token decodes JWT and sets expiration correctly."""
    token = get_test_token()

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}; Path=/; HttpOnly"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    await frigate_client._get_token()

    assert frigate_client._token_data["token"] == token
    assert frigate_client._token_data["expires"] > datetime.datetime.now(
        datetime.timezone.utc
    )


async def test_refresh_token_if_needed_without_expires(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _refresh_token_if_needed refreshes token if expired."""
    token = get_test_token()

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )
    # Ensure expires is not set
    frigate_client._token_data.pop("expires", None)

    await frigate_client._refresh_token_if_needed()
    assert frigate_client._token_data["token"] == token


async def test_refresh_token_if_needed_with_expires(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _refresh_token_if_needed refreshes token if expired."""
    token = get_test_token()

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )
    # Simulate an expired token
    frigate_client._token_data["expires"] = datetime.datetime.now(
        datetime.UTC
    ) - datetime.timedelta(hours=1)

    await frigate_client._refresh_token_if_needed()
    assert frigate_client._token_data["token"] == token


async def test_get_auth_headers(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test get_auth_headers includes Authorization header with valid token."""
    token = get_test_token()

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )
    # Pre-fetch token
    await frigate_client._get_token()
    headers = await frigate_client.get_auth_headers()

    assert headers["Authorization"] == f"Bearer {token}"


async def test_get_token_missing_set_cookie(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing Set-Cookie header."""

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint without Set-Cookie."""
        return web.Response(status=200)

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(KeyError, match="Missing Set-Cookie header in response"):
        await frigate_client._get_token()


async def test_get_token_missing_token_in_cookie(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing frigate_token in cookie."""

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint without frigate_token."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = "expires=Fri, 06 Dec 2024 20:22:35"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(KeyError, match="Missing 'frigate_token' in Set-Cookie header"):
        await frigate_client._get_token()


async def test_get_token_missing_exp_claim(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing exp claim in JWT."""
    token = jwt.encode({"sub": "test_user"}, key="secret", algorithm="HS256")

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint with token missing exp claim."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}; Path=/; HttpOnly"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(KeyError, match="JWT is missing 'exp' claim"):
        await frigate_client._get_token()


async def test_get_token_malformed_token(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing exp claim in JWT."""
    token = "ThisIsObviously a bad token"

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint with token missing exp claim."""
        response = web.Response(status=200)
        response.headers["Set-Cookie"] = f"frigate_token={token}; Path=/; HttpOnly"
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(
        ValueError, match="Failed to decode JWT token: Not enough segments"
    ):
        await frigate_client._get_token()


async def test_get_verbose_frigate_auth_error_unauthorized(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing exp claim in JWT."""

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint with token missing exp claim."""
        response = web.Response(status=401)
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(
        FrigateApiClientError, match="Unauthorized access - check credentials."
    ):
        await frigate_client._get_token()


async def test_get_verbose_frigate_auth_error_forbidden(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing exp claim in JWT."""

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint with token missing exp claim."""
        response = web.Response(status=403)
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(
        FrigateApiClientError, match="Forbidden - insufficient permissions."
    ):
        await frigate_client._get_token()


async def test_get_verbose_frigate_auth_error_teapot(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test _get_token raises KeyError for missing exp claim in JWT."""

    async def login_handler(request: web.Request) -> web.Response:
        """Simulate login endpoint with token missing exp claim."""
        response = web.Response(status=418)
        return response

    server = await start_frigate_server(
        aiohttp_server, [web.post("/api/login", login_handler)]
    )
    frigate_client = FrigateApiClient(
        str(server.make_url("/")), aiohttp_session, username="user", password="pass"
    )

    with pytest.raises(FrigateApiClientError):
        await frigate_client._get_token()


async def test_create_event(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_create_event."""
    camera = "front_door"
    event_id = "1656282822.206673-bovnfg"
    create_success = {"success": True, "message": "Event created", "event_id": event_id}

    async def create_handler(request: web.Request) -> web.Response:
        """Event create handler."""
        body = await request.json()
        assert body == {"duration": 30, "include_recording": True, "sub_label": ""}

        return web.json_response(create_success)

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.post(f"/api/events/{camera}/doorbell_press/create", create_handler),
        ],
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert (
        await frigate_client.async_create_event(camera, "doorbell_press")
        == create_success
    )


async def test_end_event(
    aiohttp_session: aiohttp.ClientSession, aiohttp_server: Any
) -> None:
    """Test async_end_event."""
    event_id = "1656282822.206673-bovnfg"
    end_success = {"success": True, "message": "Event ended", "event_id": event_id}
    end_handler = AsyncMock(return_value=web.json_response(end_success))

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.put(f"/api/events/{event_id}/end", end_handler),
        ],
    )

    frigate_client = FrigateApiClient(str(server.make_url("/")), aiohttp_session)
    assert await frigate_client.async_end_event(event_id) == end_success
    assert end_handler.called
