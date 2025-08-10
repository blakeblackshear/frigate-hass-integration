"""Test the frigate views."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
import logging
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web
from hass_web_proxy_lib.tests.utils import response_handler, ws_response_handler
import pytest

from custom_components.frigate.const import (
    ATTR_CLIENT_ID,
    ATTR_MQTT,
    CONF_NOTIFICATION_PROXY_ENABLE,
    CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS,
    DOMAIN,
)
from homeassistant.components.http.auth import async_sign_path
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


def _get_fixed_datetime() -> datetime:
    """Get a fixed-in-time datetime."""
    datetime_today = Mock(wraps=datetime)
    datetime_today.now = Mock(
        return_value=datetime.fromtimestamp(1635807720, tz=timezone.utc)
    )
    return datetime_today


FIXED_TEST_DATETIME = _get_fixed_datetime()


@pytest.fixture
async def local_frigate(hass: HomeAssistant, aiohttp_server: Any) -> Any:
    """Point the integration at a local fake Frigate server."""

    server = await start_frigate_server(
        aiohttp_server,
        [
            web.get("/vod/present/manifest.m3u8", response_handler),
            web.get("/vod/present/segment.ts", response_handler),
            web.get("/api/events/event_id/thumbnail.jpg", response_handler),
            web.get("/api/events/event_id/snapshot.jpg", response_handler),
            web.get("/api/events/event_id/clip.mp4", response_handler),
            web.get("/vod/event/event_id/master.m3u8", response_handler),
            web.get("/api/events/event_id/preview.gif", response_handler),
            web.get("/api/review/event_id/preview", response_handler),
            web.get(
                "/api/events/1577854800.123456-random/snapshot.jpg", response_handler
            ),
            web.get(
                "/api/events/1635807600.123456-random/snapshot.jpg", response_handler
            ),
            web.get(
                "/api/events/1635807359.123456-random/snapshot.jpg", response_handler
            ),
            web.get("/live/jsmpeg/front_door", ws_response_handler),
            web.get("/live/jsmpeg/querystring", ws_response_handler),
            web.get("/live/mse/front_door", ws_response_handler),
            web.get("/live/mse/querystring", ws_response_handler),
            web.get("/live/webrtc/front_door", ws_response_handler),
            web.get("/live/webrtc/querystring", ws_response_handler),
            web.get(
                "/api/front_door/start/1664067600.02/end/1664068200.03/clip.mp4",
                response_handler,
            ),
        ],
    )

    client = create_mock_frigate_client()
    client.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer token"})
    config_entry = create_mock_frigate_config_entry(
        hass, data={CONF_URL: str(server.make_url("/"))}
    )
    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )


async def test_vod_manifest_proxy(
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test vod manifest."""
    authenticated_hass_client = await hass_client()
    resp = await authenticated_hass_client.get(
        "/api/frigate/vod/present/manifest.m3u8",
    )
    assert resp.status == HTTPStatus.OK


async def test_vod_segment_proxy(
    hass: HomeAssistant,
    hass_access_token: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test vod segment."""

    refresh_token = hass.auth.async_validate_access_token(hass_access_token)
    assert refresh_token

    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    authenticated_hass_client = await hass_client()
    resp = await authenticated_hass_client.get(signed_path)
    assert resp.status == HTTPStatus.OK


async def test_vod_segment_proxy_unauthorized(
    hass: HomeAssistant,
    hass_access_token: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test vod segment."""

    authenticated_hass_client = await hass_client()

    # No secret set
    resp = await authenticated_hass_client.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTPStatus.UNAUTHORIZED

    refresh_token = hass.auth.async_validate_access_token(hass_access_token)
    assert refresh_token

    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    # No signature
    resp = await authenticated_hass_client.get("/api/frigate/vod/present/segment.ts")
    assert resp.status == HTTPStatus.UNAUTHORIZED

    # Wrong signature
    resp = await authenticated_hass_client.get(
        "/api/frigate/vod/present/segment.ts?authSig=invalid"
    )
    assert resp.status == HTTPStatus.UNAUTHORIZED

    # Modified path
    resp = await authenticated_hass_client.get(
        signed_path.replace("/api/frigate/", "/api/frigate/mod/")
    )
    assert resp.status == HTTPStatus.UNAUTHORIZED


async def test_snapshot_proxy_view(
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test straightforward snapshot requests."""

    authenticated_hass_client = await hass_client()

    resp = await authenticated_hass_client.get("/api/frigate/snapshot/event_id")
    assert resp.status == HTTPStatus.OK

    resp = await authenticated_hass_client.get("/api/frigate/snapshot/not_present")
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_recordings_proxy_view(
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test recordings proxy."""

    authenticated_hass_client = await hass_client()

    resp = await authenticated_hass_client.get(
        "/api/frigate/recording/front_door/start/1664067600.02/end/1664068200.03"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_thumbnail(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification thumbnail."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/thumbnail.jpg"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_snapshot(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification snapshot."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_event_preview(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification clip."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/event_preview.gif"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_review_preview(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification clip."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/review_preview.gif"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_hls(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification HLS."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/camera/master.m3u8"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_view_clip(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification clip."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/camera/clip.mp4"
    )
    assert resp.status == HTTPStatus.OK


async def test_notifications_proxy_other(
    local_frigate: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notification clip."""

    unauthenticated_hass_client = await hass_client_no_auth()

    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/camera/not_present"
    )
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_snapshots_with_frigate_instance_id(
    local_frigate: Any,
    hass_client: Any,
    hass: Any,
) -> None:
    """Test snapshot with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    authenticated_hass_client = await hass_client()

    # A Frigate instance id is specified.
    resp = await authenticated_hass_client.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/snapshot/event_id"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await authenticated_hass_client.get(
        "/api/frigate/NOT_A_REAL_ID/snapshot/event_id"
    )
    assert resp.status == HTTPStatus.NOT_FOUND

    # There is no default when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await authenticated_hass_client.get("/api/frigate/snapshot/event_id")
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_thumbnails_with_frigate_instance_id(
    local_frigate: Any,
    hass_client: Any,
    hass: Any,
) -> None:
    """Test snapshot with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    authenticated_hass_client = await hass_client()

    # A Frigate instance id is specified.
    resp = await authenticated_hass_client.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/thumbnail/event_id"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await authenticated_hass_client.get(
        "/api/frigate/NOT_A_REAL_ID/thumbnail/event_id"
    )
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_vod_with_frigate_instance_id(
    local_frigate: Any,
    hass_client: Any,
    hass: Any,
) -> None:
    """Test vod with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    authenticated_hass_client = await hass_client()

    # A Frigate instance id is specified.
    resp = await authenticated_hass_client.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/present/manifest.m3u8"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await authenticated_hass_client.get(
        "/api/frigate/NOT_A_REAL_ID/vod/present/manifest.m3u8"
    )
    assert resp.status == HTTPStatus.NOT_FOUND

    # There is no default when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await authenticated_hass_client.get("/api/frigate/vod/present/manifest.m3u8")
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_vod_segment_with_frigate_instance_id(
    hass: HomeAssistant,
    hass_access_token: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test vod with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    refresh_token = hass.auth.async_validate_access_token(hass_access_token)
    assert refresh_token

    signed_path = async_sign_path(
        hass,
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )

    authenticated_hass_client = await hass_client()

    # A Frigate instance id is specified.
    resp = await authenticated_hass_client.get(signed_path)
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    signed_path = async_sign_path(
        hass,
        "/api/frigate/NOT_A_REAL_ID/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )
    resp = await authenticated_hass_client.get(signed_path)
    assert resp.status == HTTPStatus.NOT_FOUND

    # There is no default when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    signed_path = async_sign_path(
        hass,
        "/api/frigate/vod/present/segment.ts",
        timedelta(seconds=5),
        refresh_token_id=refresh_token.id,
    )
    resp = await authenticated_hass_client.get(signed_path)
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_notifications_with_frigate_instance_id(
    local_frigate: Any,
    hass: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notifications with config entry ids."""

    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    assert frigate_entries

    unauthenticated_hass_client = await hass_client_no_auth()

    # A Frigate instance id is specified.
    resp = await unauthenticated_hass_client.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}"
        "/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK

    # An invalid instance id is specified.
    resp = await unauthenticated_hass_client.get(
        "/api/frigate/NOT_A_REAL_ID/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.NOT_FOUND

    # There is no default when there are multiple entries.
    create_mock_frigate_config_entry(hass, entry_id="another_id")
    resp = await unauthenticated_hass_client.get(
        "/api/frigate/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_notifications_with_disabled_option(
    local_frigate: Any,
    hass: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test notifications with config entry ids."""

    # Make another config entry with the same data but with
    # CONF_NOTIFICATION_PROXY_ENABLE disabled.
    config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        options={CONF_NOTIFICATION_PROXY_ENABLE: False},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    client.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer token"})

    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    unauthenticated_hass_client = await hass_client_no_auth()

    # Default Frigate instance should continue serving fine.
    resp = await unauthenticated_hass_client.get(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.OK

    # Private instance will not proxy notification data.
    resp = await unauthenticated_hass_client.get(
        "/api/frigate/private_id/notifications/event_id/snapshot.jpg"
    )
    assert resp.status == HTTPStatus.FORBIDDEN


async def test_notifications_with_no_expiration(
    local_frigate: Any,
    hass: Any,
    hass_client_no_auth: Any,
) -> None:
    """Test that notification events are served if they are set to not expire."""

    # Make another config entry with the same data but with
    # CONF_NOTIFICATION_PROXY_ENABLE disabled.
    config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        options={CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS: 0},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    client.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer token"})

    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    unauthenticated_hass_client = await hass_client_no_auth()

    # Fake time is 2021-11-01T19:02:00
    with patch(
        "custom_components.frigate.views.datetime.datetime", new=FIXED_TEST_DATETIME
    ):
        # Old event id should be served
        # Test event timestamp is 2020-01-01 00:00:00
        resp = await unauthenticated_hass_client.get(
            "/api/frigate/private_id/notifications/1577854800.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.OK


async def test_expired_notifications_are_forbidden(
    local_frigate: Any,
    hass_client_no_auth: Any,
    hass: Any,
) -> None:
    """Test that notification events are not served if older than expiration config."""
    config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        # for this test, notifications expire after 5 minutes from the event
        options={CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS: 5 * 60},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    client.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer token"})

    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    unauthenticated_hass_client = await hass_client_no_auth()

    # Fake time is 2021-11-01T19:02:00
    with patch(
        "custom_components.frigate.views.datetime.datetime", new=FIXED_TEST_DATETIME
    ):
        # Well-formed, not expired events should be served
        # Test event timestamp is 2021-11-01T19:00:00 - 2 minutes prior test (fake) time
        resp = await unauthenticated_hass_client.get(
            "/api/frigate/private_id/notifications/1635807600.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.OK

        # Expired event ids should not be served.
        # Test event timestamp is 2021-11-01T18:55:59 - 6:01 minutes prior test (fake) time
        resp = await unauthenticated_hass_client.get(
            "/api/frigate/private_id/notifications/1635807359.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.FORBIDDEN

        # Invalid event ids should not be served.
        resp = await unauthenticated_hass_client.get(
            "/api/frigate/private_id/notifications/invalid.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.FORBIDDEN


async def test_expired_notifications_are_served_when_authenticated(
    local_frigate: Any,
    hass_client: Any,
    hass: Any,
) -> None:
    """Test that notification events are always served if the request is authenticated."""
    config_entry = create_mock_frigate_config_entry(
        hass,
        entry_id="private_id",
        # for this test, notifications expire after 5 minutes from the event
        options={CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS: 5 * 60},
        data=hass.config_entries.async_get_entry(TEST_CONFIG_ENTRY_ID).data,
    )

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config[ATTR_MQTT][ATTR_CLIENT_ID] = "private_id"
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    client.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer token"})

    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    authenticated_hass_client = await hass_client()

    # Fake time is 2021-11-01T19:02:00
    with patch(
        "custom_components.frigate.views.datetime.datetime", new=FIXED_TEST_DATETIME
    ):
        # Expired event ids SHOULD be served since the request is authenticated.
        # Test event timestamp is 2021-11-01T18:55:59 - 6:01 minutes prior test (fake) time
        resp = await authenticated_hass_client.get(
            "/api/frigate/private_id/notifications/1635807359.123456-random/snapshot.jpg"
        )
        assert resp.status == HTTPStatus.OK


async def test_jsmpeg_ws_proxy_view(
    hass: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test JSMPEG proxying."""

    authenticated_hass_client = await hass_client()

    async with authenticated_hass_client.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/jsmpeg/front_door"
    ) as ws:
        # First message from the fixture will be the URL and headers.
        request = await ws.receive_json()
        assert request["url"].endswith("/live/jsmpeg/front_door")

        # Subsequent messages will echo back.
        await ws.send_str("Hello!")
        assert (await ws.receive_str()) == "Hello!"


async def test_mse_ws_proxy_view(
    hass: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test MSE proxying."""

    authenticated_hass_client = await hass_client()

    async with authenticated_hass_client.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/mse/front_door"
    ) as ws:
        # First message from the fixture will be the URL and headers.
        request = await ws.receive_json()
        assert request["url"].endswith("/live/mse/front_door")

        # Subsequent messages will echo back.
        await ws.send_str("Hello!")
        assert (await ws.receive_str()) == "Hello!"


async def test_webrtc_ws_proxy_view(
    hass: Any,
    local_frigate: Any,
    hass_client: Any,
) -> None:
    """Test WebRTC proxying."""

    authenticated_hass_client = await hass_client()

    async with authenticated_hass_client.ws_connect(
        f"/api/frigate/{TEST_FRIGATE_INSTANCE_ID}/webrtc/front_door"
    ) as ws:
        # First message from the fixture will be the URL and headers.
        request = await ws.receive_json()
        assert request["url"].endswith("/live/webrtc/front_door")

        # Subsequent messages will echo back.
        await ws.send_str("Hello!")
        assert (await ws.receive_str()) == "Hello!"
