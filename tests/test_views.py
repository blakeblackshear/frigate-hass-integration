"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
from datetime import timedelta
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import hdrs, web
from aiohttp.web_exceptions import HTTPUnauthorized
import pytest

from custom_components.frigate.const import (
    ATTR_CLIENT_ID,
    ATTR_MQTT,
    CONF_NOTIFICATION_PROXY_ENABLE,
    DOMAIN,
)
from homeassistant.components.http.auth import async_sign_path, setup_auth
from homeassistant.components.http.const import KEY_AUTHENTICATED
from homeassistant.components.http.forwarded import async_setup_forwarded
from homeassistant.const import (
    CONF_URL,
    HTTP_BAD_REQUEST,
    HTTP_FORBIDDEN,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)
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

    async def handler(request: web.Request) -> web.Response:
        for header in (
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_ENCODING,
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
        return web.json_response({})

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.get("/clips/present", handler),
            web.get("/vod/present/manifest.m3u8", handler),
            web.get("/vod/present/segment.ts", handler),
            web.get("/api/events/event_id/thumbnail.jpg", handler),
            web.get("/api/events/event_id/snapshot.jpg", handler),
            web.get("/api/events/event_id/clip.mp4", handler),
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
    assert resp.status == HTTP_OK


async def test_vod_segment_proxy(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod segment."""

    setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        refresh_token.id,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
    )

    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTP_OK


async def test_vod_segment_proxy_unauthorized(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod segment."""

    # No secret set
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTP_UNAUTHORIZED

    setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        refresh_token.id,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
    )

    # No signature
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTP_UNAUTHORIZED

    # Wrong signature
    resp = await hass_client_local_frigate.get(
        "/api/frigate/vod/present/segment.ts?authSig=invalid"
    )

    # Modified path
    resp = await hass_client_local_frigate.get(
        signed_path.replace("/api/frigate/", "/api/frigate/mod/")
    )
    assert resp.status == HTTP_UNAUTHORIZED


async def test_snapshot_proxy_view_success(
    hass_client_local_frigate: Any,
) -> None:
    """Test straightforward snapshot requests."""

    resp = await hass_client_local_frigate.get("/api/frigate/clips/present")
    assert resp.status == HTTP_OK

    resp = await hass_client_local_frigate.get("/api/frigate/clips/not_present")
    assert resp.status == HTTP_NOT_FOUND


async def test_snapshot_proxy_view_write_error(
    caplog: Any, hass_client_local_frigate: Any
) -> None:
    """Test snapshot request with a write error."""

    with patch(
        "custom_components.frigate.views.web.StreamResponse",
        new=ClientErrorStreamResponse,
    ):
        await hass_client_local_frigate.get("/api/frigate/clips/present")
        assert "Stream error" in caplog.text


async def test_snapshot_proxy_view_connection_reset(
    caplog: Any, hass_client_local_frigate: Any
) -> None:
    """Test snapshot request with a connection reset."""

    with patch(
        "custom_components.frigate.views.web.StreamResponse",
        new=ConnectionResetStreamResponse,
    ):
        await hass_client_local_frigate.get("/api/frigate/clips/present")
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
        await hass_client_local_frigate.get("/api/frigate/clips/present")
        assert "Reverse proxy error" in caplog.text


async def test_notifications_proxy_view_thumbnail(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification thumbnail."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg"
    )
    assert resp.status == HTTP_OK


async def test_notifications_proxy_view_snapshot(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification snapshot."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTP_OK


async def test_notifications_proxy_view_clip(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification clip."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/camera/clip.mp4"
    )
    assert resp.status == HTTP_OK


async def test_notifications_proxy_other(
    hass_client_local_frigate: Any,
) -> None:
    """Test notification clip."""

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/camera/not_present"
    )
    assert resp.status == HTTP_NOT_FOUND


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
    assert resp.status == HTTP_OK

    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg",
        headers={hdrs.X_FORWARDED_FOR: "1.2.3.4"},
    )
    assert resp.status == HTTP_OK


async def test_snapshots_with_frigate_instance_id(
    hass_client_local_frigate: Any,
    hass: Any,
) -> None:
    """Test snapshot with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/clips/present"
    )
    assert resp.status == HTTP_OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/clips/present"
    )
    assert resp.status == HTTP_BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get("/api/frigate/clips/present")
    assert resp.status == HTTP_BAD_REQUEST


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
    assert resp.status == HTTP_OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/vod/present/manifest.m3u8"
    )
    assert resp.status == HTTP_BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get("/api/frigate/vod/present/manifest.m3u8")
    assert resp.status == HTTP_BAD_REQUEST


async def test_vod_segment_with_frigate_instance_id(
    hass: HomeAssistant,
    app: Any,
    hass_access_token: Any,
    hass_client_local_frigate: Any,
) -> None:
    """Test vod with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    setup_auth(hass, app)

    refresh_token = await hass.auth.async_validate_access_token(hass_access_token)
    signed_path = async_sign_path(
        hass,
        refresh_token.id,
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/present/segment.ts",
        timedelta(seconds=5),
    )

    # A Frigate instance id is specified.
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTP_OK

    # An invalid instance id is specified.
    signed_path = async_sign_path(
        hass,
        refresh_token.id,
        "/api/frigate/NOT_A_REAL_ID/vod/present/segment.ts",
        timedelta(seconds=5),
    )
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTP_BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    signed_path = async_sign_path(
        hass,
        refresh_token.id,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
    )
    resp = await hass_client_local_frigate.get(signed_path)
    assert resp.status == HTTP_BAD_REQUEST


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
    assert resp.status == HTTP_OK

    # An invalid instance id is specified.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/NOT_A_REAL_ID/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTP_BAD_REQUEST

    # No default allowed when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await hass_client_local_frigate.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTP_BAD_REQUEST


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
    assert resp.status == HTTP_OK

    # Private instance will not proxy notification data.
    resp = await hass_client_local_frigate.get(
        "/api/frigate/private_id/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTP_FORBIDDEN
