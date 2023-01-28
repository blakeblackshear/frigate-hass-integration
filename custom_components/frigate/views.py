"""Frigate HTTP views."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import datetime
from http import HTTPStatus
from ipaddress import ip_address
import logging
from typing import Any, Optional, cast

import aiohttp
from aiohttp import hdrs, web
from aiohttp.web_exceptions import HTTPBadGateway, HTTPUnauthorized
import jwt
from multidict import CIMultiDict
from yarl import URL

from custom_components.frigate.api import FrigateApiClient
from custom_components.frigate.const import (
    ATTR_CLIENT,
    ATTR_CLIENT_ID,
    ATTR_CONFIG,
    ATTR_MQTT,
    CONF_NOTIFICATION_PROXY_ENABLE,
    CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS,
    DOMAIN,
)
from homeassistant.components.http import KEY_AUTHENTICATED, HomeAssistantView
from homeassistant.components.http.auth import DATA_SIGN_SECRET, SIGN_QUERY_PARAM
from homeassistant.components.http.const import KEY_HASS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER: logging.Logger = logging.getLogger(__name__)


def get_default_config_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Get the default Frigate config entry.

    This is for backwards compatibility for when only a single instance was
    supported. If there's more than one instance configured, then there is no
    default and the user must specify explicitly which instance they want.
    """
    frigate_entries = hass.config_entries.async_entries(DOMAIN)
    if len(frigate_entries) == 1:
        return frigate_entries[0]
    return None


def get_frigate_instance_id(config: dict[str, Any]) -> str | None:
    """Get the Frigate instance id from a Frigate configuration."""

    # Use the MQTT client_id as a way to separate the frigate instances, rather
    # than just using the config_entry_id, in order to make URLs maximally
    # relatable/findable by the user. The MQTT client_id value is configured by
    # the user in their Frigate configuration and will be unique per Frigate
    # instance (enforced in practice on the Frigate/MQTT side).
    return cast(Optional[str], config.get(ATTR_MQTT, {}).get(ATTR_CLIENT_ID))


def get_config_entry_for_frigate_instance_id(
    hass: HomeAssistant, frigate_instance_id: str
) -> ConfigEntry | None:
    """Get a ConfigEntry for a given frigate_instance_id."""

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        config = hass.data[DOMAIN].get(config_entry.entry_id, {}).get(ATTR_CONFIG, {})
        if config and get_frigate_instance_id(config) == frigate_instance_id:
            return config_entry
    return None


def get_client_for_frigate_instance_id(
    hass: HomeAssistant, frigate_instance_id: str
) -> FrigateApiClient | None:
    """Get a client for a given frigate_instance_id."""

    config_entry = get_config_entry_for_frigate_instance_id(hass, frigate_instance_id)
    if config_entry:
        return cast(
            FrigateApiClient,
            hass.data[DOMAIN].get(config_entry.entry_id, {}).get(ATTR_CLIENT),
        )
    return None


def get_frigate_instance_id_for_config_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> ConfigEntry | None:
    """Get a frigate_instance_id for a ConfigEntry."""

    config = hass.data[DOMAIN].get(config_entry.entry_id, {}).get(ATTR_CONFIG, {})
    return get_frigate_instance_id(config) if config else None


def async_setup(hass: HomeAssistant) -> None:
    """Set up the views."""
    session = async_get_clientsession(hass)
    hass.http.register_view(JSMPEGProxyView(session))
    hass.http.register_view(MSEProxyView(session))
    hass.http.register_view(WebRTCProxyView(session))
    hass.http.register_view(NotificationsProxyView(session))
    hass.http.register_view(SnapshotsProxyView(session))
    hass.http.register_view(RecordingProxyView(session))
    hass.http.register_view(ThumbnailsProxyView(session))
    hass.http.register_view(VodProxyView(session))
    hass.http.register_view(VodSegmentProxyView(session))


# These proxies are inspired by:
#  - https://github.com/home-assistant/supervisor/blob/main/supervisor/api/ingress.py


class ProxyView(HomeAssistantView):  # type: ignore[misc]
    """HomeAssistant view."""

    requires_auth = True

    def __init__(self, websession: aiohttp.ClientSession):
        """Initialize the frigate clips proxy view."""
        self._websession = websession

    def _get_config_entry_for_request(
        self, request: web.Request, frigate_instance_id: str | None
    ) -> ConfigEntry | None:
        """Get a ConfigEntry for a given request."""
        hass = request.app[KEY_HASS]

        if frigate_instance_id:
            return get_config_entry_for_frigate_instance_id(hass, frigate_instance_id)
        return get_default_config_entry(hass)

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        raise NotImplementedError  # pragma: no cover

    def _permit_request(
        self, request: web.Request, config_entry: ConfigEntry, **kwargs: Any
    ) -> bool:
        """Determine whether to permit a request."""
        return True

    async def get(
        self,
        request: web.Request,
        **kwargs: Any,
    ) -> web.Response | web.StreamResponse | web.WebSocketResponse:
        """Route data to service."""
        try:
            return await self._handle_request(request, **kwargs)

        except aiohttp.ClientError as err:
            _LOGGER.debug("Reverse proxy error for %s: %s", request.rel_url, err)

        raise HTTPBadGateway() from None

    @staticmethod
    def _get_query_params(request: web.Request) -> Mapping[str, str]:
        """Get the query params to send upstream."""
        return {k: v for k, v in request.query.items() if k != "authSig"}

    async def _handle_request(
        self,
        request: web.Request,
        frigate_instance_id: str | None = None,
        **kwargs: Any,
    ) -> web.Response | web.StreamResponse:
        """Handle route for request."""
        config_entry = self._get_config_entry_for_request(request, frigate_instance_id)
        if not config_entry:
            return web.Response(status=HTTPStatus.BAD_REQUEST)

        if not self._permit_request(request, config_entry, **kwargs):
            return web.Response(status=HTTPStatus.FORBIDDEN)

        full_path = self._create_path(**kwargs)
        if not full_path:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        url = str(URL(config_entry.data[CONF_URL]) / full_path)
        data = await request.read()
        source_header = _init_header(request)

        async with self._websession.request(
            request.method,
            url,
            headers=source_header,
            params=self._get_query_params(request),
            allow_redirects=False,
            data=data,
        ) as result:
            headers = _response_header(result)

            # Stream response
            response = web.StreamResponse(status=result.status, headers=headers)
            response.content_type = result.content_type

            try:
                await response.prepare(request)
                async for data in result.content.iter_any():
                    await response.write(data)

            except (aiohttp.ClientError, aiohttp.ClientPayloadError) as err:
                _LOGGER.debug("Stream error for %s: %s", request.rel_url, err)
            except ConnectionResetError:
                # Connection is reset/closed by peer.
                pass

            return response


class SnapshotsProxyView(ProxyView):
    """A proxy for snapshots."""

    url = "/api/frigate/{frigate_instance_id:.+}/snapshot/{eventid:.*}"
    extra_urls = ["/api/frigate/snapshot/{eventid:.*}"]

    name = "api:frigate:snapshots"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"api/events/{kwargs['eventid']}/snapshot.jpg"


class RecordingProxyView(ProxyView):
    """A proxy for recordings."""

    url = "/api/frigate/{frigate_instance_id:.+}/recording/{camera:.+}/start/{start:[.0-9]+}/end/{end:[.0-9]*}"
    extra_urls = [
        "/api/frigate/recording/{camera:.+}/start/{start:[.0-9]+}/end/{end:[.0-9]*}"
    ]

    name = "api:frigate:recording"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return (
            f"api/{kwargs['camera']}/start/{kwargs['start']}"
            + f"/end/{kwargs['end']}/clip.mp4"
        )


class ThumbnailsProxyView(ProxyView):
    """A proxy for snapshots."""

    url = "/api/frigate/{frigate_instance_id:.+}/thumbnail/{eventid:.*}"

    name = "api:frigate:thumbnails"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"api/events/{kwargs['eventid']}/thumbnail.jpg"


class NotificationsProxyView(ProxyView):
    """A proxy for notifications."""

    url = "/api/frigate/{frigate_instance_id:.+}/notifications/{event_id}/{path:.*}"
    extra_urls = ["/api/frigate/notifications/{event_id}/{path:.*}"]

    name = "api:frigate:notification"
    requires_auth = False

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        path, event_id = kwargs["path"], kwargs["event_id"]
        if path == "thumbnail.jpg":
            return f"api/events/{event_id}/thumbnail.jpg"

        if path == "snapshot.jpg":
            return f"api/events/{event_id}/snapshot.jpg"

        if path.endswith("clip.mp4"):
            return f"api/events/{event_id}/clip.mp4"
        return None

    def _permit_request(
        self, request: web.Request, config_entry: ConfigEntry, **kwargs: Any
    ) -> bool:
        """Determine whether to permit a request."""

        is_notification_proxy_enabled = bool(
            config_entry.options.get(CONF_NOTIFICATION_PROXY_ENABLE, True)
        )

        # If proxy is disabled, immediately reject
        if not is_notification_proxy_enabled:
            return False

        # Authenticated requests are always allowed.
        if request[KEY_AUTHENTICATED]:
            return True

        # If request is not authenticated, check whether it is expired.
        notification_expiration_seconds = int(
            config_entry.options.get(CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS, 0)
        )

        # If notification events never expire, immediately permit.
        if notification_expiration_seconds == 0:
            return True

        try:
            event_id_timestamp = int(kwargs["event_id"].partition(".")[0])
            event_datetime = datetime.datetime.fromtimestamp(
                event_id_timestamp, tz=datetime.timezone.utc
            )
            now_datetime = datetime.datetime.now(tz=datetime.timezone.utc)
            expiration_datetime = event_datetime + datetime.timedelta(
                seconds=notification_expiration_seconds
            )

            # Otherwise, permit only if notification event is not expired
            return now_datetime.timestamp() <= expiration_datetime.timestamp()
        except ValueError:
            _LOGGER.warning(
                "The event id %s does not have a valid format.", kwargs["event_id"]
            )
            return False


class VodProxyView(ProxyView):
    """A proxy for vod playlists."""

    url = "/api/frigate/{frigate_instance_id:.+}/vod/{path:.+}/{manifest:.+}.m3u8"
    extra_urls = ["/api/frigate/vod/{path:.+}/{manifest:.+}.m3u8"]

    name = "api:frigate:vod:manifest"

    @staticmethod
    def _get_query_params(request: web.Request) -> Mapping[str, str]:
        """Get the query params to send upstream."""
        return request.query

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"vod/{kwargs['path']}/{kwargs['manifest']}.m3u8"


class VodSegmentProxyView(ProxyView):
    """A proxy for vod segments."""

    url = "/api/frigate/{frigate_instance_id:.+}/vod/{path:.+}/{segment:.+}.{extension:(ts|m4s|mp4)}"
    extra_urls = ["/api/frigate/vod/{path:.+}/{segment:.+}.{extension:(ts|m4s|mp4)}"]

    name = "api:frigate:vod:segment"
    requires_auth = False

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"vod/{kwargs['path']}/{kwargs['segment']}.{kwargs['extension']}"

    async def _async_validate_signed_manifest(self, request: web.Request) -> bool:
        """Validate the signature for the manifest of this segment."""
        hass = request.app[KEY_HASS]
        secret = hass.data.get(DATA_SIGN_SECRET)
        signature = request.query.get(SIGN_QUERY_PARAM)

        if signature is None:
            _LOGGER.warning("Missing authSig query parameter on VOD segment request.")
            return False

        try:
            claims = jwt.decode(
                signature, secret, algorithms=["HS256"], options={"verify_iss": False}
            )
        except jwt.InvalidTokenError:
            _LOGGER.warning("Invalid JWT token for VOD segment request.")
            return False

        # Check that the base path is the same as what was signed
        check_path = request.path.rsplit("/", maxsplit=1)[0]
        if not claims["path"].startswith(check_path):
            _LOGGER.warning("%s does not start with %s", claims["path"], check_path)
            return False

        return True

    async def get(
        self,
        request: web.Request,
        **kwargs: Any,
    ) -> web.Response | web.StreamResponse | web.WebSocketResponse:
        """Route data to service."""

        if not await self._async_validate_signed_manifest(request):
            raise HTTPUnauthorized()

        return await super().get(request, **kwargs)


class WebsocketProxyView(ProxyView):
    """A simple proxy for websockets."""

    async def _proxy_msgs(
        self,
        ws_in: aiohttp.ClientWebSocketResponse | web.WebSocketResponse,
        ws_out: aiohttp.ClientWebSocketResponse | web.WebSocketResponse,
    ) -> None:

        async for msg in ws_in:
            try:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await ws_out.send_str(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await ws_out.send_bytes(msg.data)
                elif msg.type == aiohttp.WSMsgType.PING:
                    await ws_out.ping()
                elif msg.type == aiohttp.WSMsgType.PONG:
                    await ws_out.pong()
            except ConnectionResetError:
                return

    async def _handle_request(
        self,
        request: web.Request,
        frigate_instance_id: str | None = None,
        **kwargs: Any,
    ) -> web.Response | web.StreamResponse:
        """Handle route for request."""

        config_entry = self._get_config_entry_for_request(request, frigate_instance_id)
        if not config_entry:
            return web.Response(status=HTTPStatus.BAD_REQUEST)

        if not self._permit_request(request, config_entry, **kwargs):
            return web.Response(status=HTTPStatus.FORBIDDEN)

        full_path = self._create_path(**kwargs)
        if not full_path:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        req_protocols = []
        if hdrs.SEC_WEBSOCKET_PROTOCOL in request.headers:
            req_protocols = [
                str(proto.strip())
                for proto in request.headers[hdrs.SEC_WEBSOCKET_PROTOCOL].split(",")
            ]

        ws_to_user = web.WebSocketResponse(
            protocols=req_protocols, autoclose=False, autoping=False
        )
        await ws_to_user.prepare(request)

        # Preparing
        url = str(URL(config_entry.data[CONF_URL]) / full_path)
        source_header = _init_header(request)

        # Support GET query
        if request.query_string:
            url = f"{url}?{request.query_string}"

        async with self._websession.ws_connect(
            url,
            headers=source_header,
            protocols=req_protocols,
            autoclose=False,
            autoping=False,
        ) as ws_to_frigate:
            await asyncio.wait(
                [
                    asyncio.create_task(self._proxy_msgs(ws_to_frigate, ws_to_user)),
                    asyncio.create_task(self._proxy_msgs(ws_to_user, ws_to_frigate)),
                ],
                return_when=asyncio.tasks.FIRST_COMPLETED,
            )
        return ws_to_user


class JSMPEGProxyView(WebsocketProxyView):
    """A proxy for JSMPEG websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/jsmpeg/{path:.+}"
    extra_urls = ["/api/frigate/jsmpeg/{path:.+}"]

    name = "api:frigate:jsmpeg"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"live/jsmpeg/{kwargs['path']}"


class MSEProxyView(WebsocketProxyView):
    """A proxy for MSE websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/mse/{path:.+}"
    extra_urls = ["/api/frigate/mse/{path:.+}"]

    name = "api:frigate:mse"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"live/mse/{kwargs['path']}"


class WebRTCProxyView(WebsocketProxyView):
    """A proxy for WebRTC websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/webrtc/{path:.+}"
    extra_urls = ["/api/frigate/webrtc/{path:.+}"]

    name = "api:frigate:webrtc"

    def _create_path(self, **kwargs: Any) -> str | None:
        """Create path."""
        return f"live/webrtc/{kwargs['path']}"


def _init_header(request: web.Request) -> CIMultiDict | dict[str, str]:
    """Create initial header."""
    headers = {}

    # filter flags
    for name, value in request.headers.items():
        if name in (
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_ENCODING,
            hdrs.SEC_WEBSOCKET_EXTENSIONS,
            hdrs.SEC_WEBSOCKET_PROTOCOL,
            hdrs.SEC_WEBSOCKET_VERSION,
            hdrs.SEC_WEBSOCKET_KEY,
            hdrs.HOST,
        ):
            continue
        headers[name] = value

    # Set X-Forwarded-For
    forward_for = request.headers.get(hdrs.X_FORWARDED_FOR)
    assert request.transport
    connected_ip = ip_address(request.transport.get_extra_info("peername")[0])
    if forward_for:
        forward_for = f"{forward_for}, {connected_ip!s}"
    else:
        forward_for = f"{connected_ip!s}"
    headers[hdrs.X_FORWARDED_FOR] = forward_for

    # Set X-Forwarded-Host
    forward_host = request.headers.get(hdrs.X_FORWARDED_HOST)
    if not forward_host:
        forward_host = request.host
    headers[hdrs.X_FORWARDED_HOST] = forward_host

    # Set X-Forwarded-Proto
    forward_proto = request.headers.get(hdrs.X_FORWARDED_PROTO)
    if not forward_proto:
        forward_proto = request.url.scheme
    headers[hdrs.X_FORWARDED_PROTO] = forward_proto

    return headers


def _response_header(response: aiohttp.ClientResponse) -> dict[str, str]:
    """Create response header."""
    headers = {}

    for name, value in response.headers.items():
        if name in (
            hdrs.TRANSFER_ENCODING,
            # Removing Content-Length header for streaming responses
            #   prevents seeking from working for mp4 files
            # hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_TYPE,
            hdrs.CONTENT_ENCODING,
            # Strips inbound CORS response headers since the aiohttp_cors
            # library will assert that they are not already present for CORS
            # requests.
            hdrs.ACCESS_CONTROL_ALLOW_ORIGIN,
            hdrs.ACCESS_CONTROL_ALLOW_CREDENTIALS,
            hdrs.ACCESS_CONTROL_EXPOSE_HEADERS,
        ):
            continue
        headers[name] = value

    return headers
