"""Frigate HTTP views."""
from __future__ import annotations

from ipaddress import ip_address
import logging
from typing import Any

import aiohttp
from aiohttp import hdrs, web
from aiohttp.web_exceptions import HTTPBadGateway
from multidict import CIMultiDict
from yarl import URL

from custom_components.frigate.const import DOMAIN
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.const import KEY_HASS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, HTTP_BAD_REQUEST, HTTP_NOT_FOUND
from homeassistant.core import HomeAssistant

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


class ProxyView(HomeAssistantView):
    """HomeAssistant view."""

    requires_auth = True

    def __init__(self, websession: aiohttp.ClientSession):
        """Initialize the frigate clips proxy view."""
        self._websession = websession

    def _get_base_url(
        self, request: web.Request, config_entry_id: str | None
    ) -> str | None:
        """Get a Frigate base URL."""
        hass = request.app[KEY_HASS]

        if config_entry_id:
            entry = hass.config_entries.async_get_entry(config_entry_id)
            if entry:
                return entry.data[CONF_URL]
        else:
            default_config_entry = get_default_config_entry(hass)
            if default_config_entry:
                return default_config_entry.data[CONF_URL]
        return None

    def _create_path(self, **kwargs) -> str | None:
        """Create path."""
        raise NotImplementedError  # pragma: no cover

    async def get(
        self,
        request: web.Request,
        **kwargs,
    ) -> web.Response | web.StreamResponse | web.WebSocketResponse:
        """Route data to service."""
        try:
            return await self._handle_request(request, **kwargs)

        except aiohttp.ClientError as err:
            _LOGGER.debug("Reverse proxy error for %s: %s", request.rel_url, err)

        raise HTTPBadGateway() from None

    async def _handle_request(
        self,
        request: web.Request,
        path: str,
        config_entry_id: str | None = None,
        **kwargs: Any,
    ) -> web.Response | web.StreamResponse:
        """Handle route for request."""
        base_url = self._get_base_url(request, config_entry_id)
        if not base_url:
            return web.Response(status=HTTP_BAD_REQUEST)

        path = self._create_path(path=path, **kwargs)
        if not path:
            return web.Response(status=HTTP_NOT_FOUND)

        url = str(URL(base_url) / path)
        data = await request.read()
        source_header = _init_header(request)

        async with self._websession.request(
            request.method,
            url,
            headers=source_header,
            params=request.query,
            allow_redirects=False,
            data=data,
        ) as result:
            headers = _response_header(result)

            # Stream response
            response = web.StreamResponse(status=result.status, headers=headers)
            response.content_type = result.content_type

            try:
                await response.prepare(request)
                async for data in result.content.iter_chunked(4096):
                    await response.write(data)

            except (aiohttp.ClientError, aiohttp.ClientPayloadError) as err:
                _LOGGER.debug("Stream error for %s: %s", request.rel_url, err)

            return response


class ClipsProxyView(ProxyView):
    """A proxy for clips."""

    url = "/api/frigate/{config_entry_id:.+}/clips/{path:.*}"
    extra_urls = ["/api/frigate/clips/{path:.*}"]

    name = "api:frigate:clips"

    def _create_path(self, path: str) -> str:
        """Create path."""
        return f"clips/{path}"


class RecordingsProxyView(ProxyView):
    """A proxy for recordings."""

    url = "/api/frigate/{config_entry_id:.+}/recordings/{path:.*}"
    extra_urls = ["/api/frigate/recordings/{path:.*}"]

    name = "api:frigate:recordings"

    def _create_path(self, path: str) -> str:
        """Create path."""
        return f"recordings/{path}"


class NotificationsProxyView(ProxyView):
    """A proxy for notifications."""

    url = "/api/frigate/{config_entry_id:.+}/notifications/{event_id}/{path:.*}"
    extra_urls = ["/api/frigate/notifications/{event_id}/{path:.*}"]

    name = "api:frigate:notification"
    requires_auth = False

    def _create_path(self, event_id: str, path: str) -> str | None:
        """Create path."""
        if path == "thumbnail.jpg":
            return f"api/events/{event_id}/thumbnail.jpg"

        if path == "snapshot.jpg":
            return f"api/events/{event_id}/snapshot.jpg"

        camera = path.split("/")[0]
        if path.endswith("clip.mp4"):
            return f"clips/{camera}-{event_id}.mp4"


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
        ):
            continue
        headers[name] = value

    # Set X-Forwarded-For
    forward_for = request.headers.get(hdrs.X_FORWARDED_FOR)
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
        ):
            continue
        headers[name] = value

    return headers
