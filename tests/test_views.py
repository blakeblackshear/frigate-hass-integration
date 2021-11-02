"""Test the frigate binary sensor."""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta
from http import HTTPStatus
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import hdrs, web
from aiohttp.web_exceptions import HTTPUnauthorized
import pytest

from custom_components.frigate import views
from custom_components.frigate.const import (
    ATTR_CLIENT_ID,
    ATTR_MQTT,
    CONF_EXPIRE_NOTIFICATIONS_AFTER_MINS,
    CONF_NOTIFICATION_PROXY_ENABLE,
    DOMAIN,
)
from homeassistant.components.http.auth import async_setup_auth, async_sign_path
from homeassistant.components.http.const import KEY_AUTHENTICATED
from homeassistant.components.http.forwarded import async_setup_forwarded
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_FRIGATE_INSTANCE_ID,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
    setup_mock_frigate_config_entry,
    start_frigate_server,
)

_LOGGER = logging.getLogger(__name__)


class ClientErrorStreamResponse(web.StreamResponse):
    """StreamResponse for testing purposes that raises a ClientError."""

    async def write(self, data: bytes) -> None:
        """Write data."""
        raise aiohttp.ClientError


class ConnectionResetStreamResponse(web.StreamResponse):
    """StreamResponse for testing purposes that raises a ConnectionResetError."""

    async def write(self, data: bytes) -> None:
        """Write data."""
        raise ConnectionResetError


class FakeAsyncContextManager:
    """Fake AsyncContextManager for testing purposes."""

    async def __aenter__(self, *args: Any, **kwargs: Any) -> FakeAsyncContextManager:
        """Context manager enter."""
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        """Context manager exit."""


async def mock_handler(request: Any) -> Any:
    """Return if request was authenticated."""
    if not request[KEY_AUTHENTICATED]:
        raise HTTPUnauthorized

    user = request.get("hass_user")
    user_id = user.id if user else None

    return web.json_response(status=200, data={"user_id": user_id})


@pytest.fixture
def app(hass: HomeAssistant) -> Any:
    """Fixture to set up a web.Application."""
    app = web.Application()
    app["hass"] = hass
    app.router.add_get("/", mock_handler)
    async_setup_forwarded(app, True, [])
    return app


@pytest.fixture
async def hass_client_local_frigate(
    hass: HomeAssistant, hass_client: Any, aiohttp_server: Any
) -> Any:
    """Point the integration at a local fake Frigate server."""

    def _assert_expected_headers(request: web.Request, allow_ws: bool = False) -> None:
        assert hdrs.CONTENT_ENCODING not in request.headers

        if not allow_ws:
            for header in (
                hdrs.SEC_WEBSOCKET_EXTENSIONS,
                hdrs.SEC_WEBSOCKET_PROTOCOL,
                hdrs.SEC_WEBSOCKET_VERSION,
                hdrs.SEC_WEBSOCKET_KEY,
            ):
                assert header not in request.headers

        for header in (
            hdrs.X_FORWARDED_HOST,
            hdrs.X_FORWARDED_PROTO,
            hdrs.X_FORWARDED_FOR,
        ):
            assert header in request.headers

    async def ws_qs_echo_handler(request: web.Request) -> web.WebSocketResponse:
        """Verify the query string and act as echo handler."""
        assert request.query["key"] == "value"
        return await ws_echo_handler(request)

    async def ws_echo_handler(request: web.Request) -> web.WebSocketResponse:
        """Act as echo handler."""
        _assert_expected_headers(request, allow_ws=True)

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws.send_bytes(msg.data)
        return ws

    async def handler(request: web.Request) -> web.Response:
        _assert_expected_headers(request)
        return web.json_response({})

    async def qs_handler(request: web.Request) -> web.Response:
        """Verify the query string."""
        assert request.query["key"] == "value"
        return await handler(request)

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.get("/vod/present/manifest.m3u8", handler),
            web.get("/vod/present/segment.ts", handler),
            web.get("/api/events/event_id/thumbnail.jpg", handler),
            web.get("/api/events/event_id/snapshot.jpg", handler),
            web.get("/api/events/event_id/clip.mp4", handler),
            web.get("/api/events/1577854800.123456-random/snapshot.jpg", handler),
            web.get("/api/events/1635807600.123456-random/snapshot.jpg", handler),
            web.get("/api/events/1635807359.123456-random/snapshot.jpg", handler),
            web.get("/live/front_door", ws_echo_handler),
            web.get("/live/querystring", ws_qs_echo_handler),
        ],
    )

    client = create_mock_frigate_client()
    config_entry = create_mock_frigate_config_entry(
        hass, data={CONF_URL: str(server.make_url("/"))}
    )
    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    return await hass_client()


async def test_vod_manifest_proxy(
    hass_client_local_frigate: Any,
) -> None:
    """Test vod manifest."""

    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/manifest.m3u8")
    assert resp.status == HTTPStatus.OK


async def test_vod_segment_proxy(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod segment."""

    await async_setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTPStatus.OK


async def test_vod_segment_proxy_unauthorized(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod segment."""

    # No secret set
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTPStatus.UNAUTHORIZED

    await async_setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    # No signature
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTPStatus.UNAUTHORIZED

    # Wrong signature
    resp = await hass_client_local_frigate.get(
        "/api/frigate/vod/present/segment.ts?authSig=invalid"
    )

    # Modified path
    resp = await hass_client_local_frigate.get(
        signed_path.replace("/api/frigate/", "/api/frigate/mod/")
    )
    assert resp.status == HTTPStatus.UNAUTHORIZED


async def test_snapshot_proxy_view_success(
    hass_client_local_frigate: Any,
) -> None:
    """Test straightforward snapshot requests."""
    resp = await hass_client_local_frigate.get("/api/frigate/snapshot/event_id")
    assert resp.status == HTTPStatus.OK

    resp = await hass_client_local_frigate.get("/api/frigate/snapshot/not_present")
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_snapshot_proxy_view_write_error(
    caplog: Any, hass_client_local_frigate: Any
) -> None:
    """Test snapshot request with a write error."""

    with patch(
        "custom_components.frigate.views.web.StreamResponse",
        new=ClientErrorStreamResponse,
    ):
        await hass_client_local_frigate.get("/api/frigate/snapshot/event_id")
        assert "Stream error" in caplog.text


async def test_snapshot_proxy_view_connection_reset(
    caplog: Any, hass_client_local_frigate: Any
) -> None:
    """Test snapshot request with a connection reset."""

    with patch(
        "custom_components.frigate.views.web.StreamResponse",
        new=ConnectionResetStreamResponse,
    ):
        await hass_client_local_frigate.get("/api/frigate/snapshot/event_id")
        assert "Stream error" not in caplog.text


async def test_snapshot_proxy_view_read_error(
    hass: HomeAssistant, caplog: Any, hass_client_local_frigate: Any
) -> None:
    """Test snapshot request with a read error."""

    mock_request = MagicMock(FakeAsyncContextManager())
    mock_request.side_effect = aiohttp.ClientError

    with patch.object(
        hass.helpers.aiohttp_client.async_get_clientsession(),
        "request",
        new=mock_request,
    ):
        await hass_client_local_frigate.get("/api/frigate/snapshot/event_id")
        assert "Reverse proxy error" in caplog.text


async def test_notifications_proxy_view_thumbnail(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification thumbnail."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_snapshot(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification snapshot."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_clip(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification clip."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/camera/clip.mp4"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_other(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification clip."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/camera/not_present"
    )
    assert resp.status == HTTPStatus.NOT_FOUND


@pytest.mark.allow_proxy
async def test_headers(
    hass: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test proxy headers are added and respected."""
    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg",
        headers={hdrs.CONTENT_ENCODING: "foo"},
    )
    assert resp.status == HTTPStatus.OK

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg",
        headers={hdrs.X_FORWARDED_FOR: "1.2.3.4"},
    )
    assert resp.status == HTTPStatus.OK


async def test_snapshots_with_frigate_instance_id(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test snapshot with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/snapshot/event_id"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/snapshot/event_id"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get("/api/frigate/snapshot/event_id")
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_thumbnails_with_frigate_instance_id(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test snapshot with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/thumbnail/event_id"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/thumbnail/event_id"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_vod_with_frigate_instance_id(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test vod with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/present/manifest.m3u8"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/vod/present/manifest.m3u8"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/manifest.m3u8")
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_vod_segment_with_frigate_instance_id(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    await async_setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    signed_path = async_sign_path(
        hass,
        "/api/frigate/NOT_A_REAL_ID/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTPStatus.BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_notifications_with_frigate_instance_id(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test notifications with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}"
        "/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_notifications_with_disabled_option(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test notifications with config entry ids."""

    # Make another config entry with the same data but with
    # CONF_NOTIFICATION_PROXY_ENABLE disabled.
    private_config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        options={CONF_NOTIFICATION_PROXY_ENABLE: False},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    private_config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    private_config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    private_client = create_mock_frigate_client()
    private_client.async_get_config = AsyncMock(return_value=private_config)

    await setup_mock_frigate_config_entry(
        hass, config_entry=private_config_entry, client=private_client
    )

    # Default Frigate instance should continue serving fine.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK

    # Private instance will not proxy notification data.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/private_id/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.FORBIDDEN

async def test_notifications_with_no_expiration(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test that notification events are served if they are set to not expire."""

    # Make another config entry with the same data but with
    # CONF_NOTIFICATION_PROXY_ENABLE disabled.
    private_config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        options={CONF_EXPIRE_NOTIFICATIONS_AFTER_MINS: 0},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    private_config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    private_config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    private_client = create_mock_frigate_client()
    private_client.async_get_config = AsyncMock(return_value=private_config)

    await setup_mock_frigate_config_entry(
        hass, config_entry=private_config_entry, client=private_client
    )

    # Fake time is 2021-11-01T19:02:00
    with patch("custom_components.frigate.views.NotificationsProxyView._get_current_datetime",
    return_value=datetime(2021, 11, 1, 19, 2, 00, 000000)):

        # Old event id should be vended
        # Test event timestamp is 2020-01-01 00:00:00
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/private_id/notifications/1577854800.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.OK

async def test_get_current_datetime() -> None:
    """Test datetime helper."""
    datetime_1 = views.NotificationsProxyView._get_current_datetime()
    datetime_2 = views.NotificationsProxyView._get_current_datetime()
    assert isinstance(datetime_1, datetime)
    assert isinstance(datetime_2, datetime)
    assert datetime_1 <= datetime_2

async def test_expired_notifications_are_not_served(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test that notification events are not served if older than expiration config."""
    private_config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        # for this test, notifications expire after 5 minutes from the event
        options={CONF_EXPIRE_NOTIFICATIONS_AFTER_MINS: 5},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    private_config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    private_config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    private_client = create_mock_frigate_client()
    private_client.async_get_config = AsyncMock(return_value=private_config)

    await setup_mock_frigate_config_entry(
        hass, config_entry=private_config_entry, client=private_client
    )

    # Fake time is 2021-11-01T19:02:00
    with patch("custom_components.frigate.views.NotificationsProxyView._get_current_datetime",
    return_value=datetime(2021, 11, 1, 19, 2, 00, 000000)):

        # Well-formed, not expired events should be vended
        # Test event timestamp is 2021-11-01T19:00:00 - 2 minutes prior test (fake) time
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/private_id/notifications/1635807600.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.OK

        # Expired event ids should not be vended
        # Test event timestamp is 2021-11-01T18:55:59 - 6:01 minutes prior test (fake) time
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/private_id/notifications/1635807359.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.FORBIDDEN

        # Invalid event ids should not be vended
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/private_id/notifications/invalid.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.FORBIDDEN


async def test_jsmpeg_text_binary(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test JSMPEG proxying text/binary data."""
    async with hass_client_local_frigate.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
    ) as ws:
        # Test sending text data.
        result = await asyncio.gather(
            ws.send_str("hello!"),
            ws.receive(),
        )
        assert result[1].type == aiohttp.WSMsgType.TEXT
        assert result[1].data == "hello!"

        # Test sending binary data.
        result = await asyncio.gather(
            ws.send_bytes(b"\x00\x01"),
            ws.receive(),
        )

        assert result[1].type == aiohttp.WSMsgType.BINARY
        assert result[1].data == b"\x00\x01"


async def test_jsmpeg_frame_type_ping_pong(
    hass_client_local_frigate: Any,
) -> None:
    """Test JSMPEG proxying handles ping-pong."""

    async with hass_client_local_frigate.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
    ) as ws:
        await ws.ping()

        # Push some data through after the ping.
        result = await asyncio.gather(
            ws.send_bytes(b"\x00\x01"),
            ws.receive(),
        )
        assert result[1].type == aiohttp.WSMsgType.BINARY
        assert result[1].data == b"\x00\x01"


async def test_ws_proxy_specify_protocol(
    hass_client_local_frigate: Any,
) -> None:
    """Test websocket proxy handles the SEC_WEBSOCKET_PROTOCOL header."""

    ws = await hass_client_local_frigate.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door",
        headers={hdrs.SEC_WEBSOCKET_PROTOCOL: "foo,bar"},
    )
    assert ws
    await ws.close()


async def test_ws_proxy_query_string(
    hass_client_local_frigate: Any,
) -> None:
    """Test websocket proxy passes on the querystring."""

    async with hass_client_local_frigate.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/querystring?key=value",
    ) as ws:
        result = await asyncio.gather(
            ws.send_str("hello!"),
            ws.receive(),
        )
        assert result[1].type == aiohttp.WSMsgType.TEXT
        assert result[1].data == "hello!"


async def test_jsmpeg_connection_reset(
    hass_client_local_frigate: Any,
) -> None:
    """Test JSMPEG proxying handles connection resets."""

    # Tricky: This test is intended to test a ConnectionResetError to the
    # Frigate server, which is the _second_ call to send*. The first call (from
    # this test) needs to succeed.
    real_send_str = views.aiohttp.web.WebSocketResponse.send_str

    called_once = False

    async def send_str(*args: Any, **kwargs: Any) -> None:
        nonlocal called_once
        if called_once:
            raise ConnectionResetError
        else:
            called_once = True
            return await real_send_str(*args, **kwargs)

    with patch(
        "custom_components.frigate.views.aiohttp.ClientWebSocketResponse.send_str",
        new=send_str,
    ):
        async with hass_client_local_frigate.ws_connect(
            f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
        ) as ws:
            await ws.send_str("data")


async def test_ws_proxy_bad_instance_id(
    hass_client_local_frigate: Any,
) -> None:
    """Test websocket proxy handles bad instance id."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/jsmpeg/front_door"
    )
    assert resp.status == HTTPStatus.BAD_REQUEST


async def test_ws_proxy_forbidden(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test websocket proxy handles forbidden paths."""

    # Note: The ability to forbid websocket proxy calls is currently not used,
    # but included for completeness and feature combatability with the other
    # proxies. As such, there's no 'genuine' way to test this other than mocking
    # out the call to _permit_request.

    with patch(
        "custom_components.frigate.views.WebsocketProxyView._permit_request",
        return_value=False,
    ):
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
        )
        assert resp.status == HTTPStatus.FORBIDDEN


async def test_ws_proxy_missing_path(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test websocket proxy handles missing/invalid paths."""

    # Note: With current uses of the WebsocketProxy it's not possible to have a
    # bad/missing path. Since that may not be the case in future for other views
    # that inherit from WebsocketProxyView, this is tested here.
    with patch(
        "custom_components.frigate.views.JSMPEGProxyView._create_path",
        return_value=None,
    ):
        resp = await hass_client_local_frigate.get(
            f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
        )
        assert resp.status == HTTPStatus.NOT_FOUND
