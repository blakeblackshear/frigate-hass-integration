"""Frigate HTTP views."""

from __future__ import annotations

from collections.abc import Mapping
import datetime
import logging
import os
from typing import Any, Optional, cast

from aiohttp import web
from hass_web_proxy_lib import (
    HASSWebProxyLibForbiddenRequestError,
    HASSWebProxyLibNotFoundRequestError,
    HASSWebProxyLibUnauthorizedRequestError,
    ProxiedURL,
    ProxyView,
    WebsocketProxyView,
)
import jwt
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
from homeassistant.components.http import KEY_AUTHENTICATED
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


def get_client_for_config_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> FrigateApiClient | None:
    """Get a client for a given ConfigEntry."""
    if config_entry:
        return cast(
            Optional[FrigateApiClient],
            hass.data[DOMAIN].get(config_entry.entry_id, {}).get(ATTR_CLIENT),
        )
    # We don't expect a config entry to ever not have a client, but just in case:
    return None  # pragma: no cover


def get_frigate_instance_id_for_config_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> str | None:
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


class FrigateProxyViewMixin:
    """A mixin for proxying Frigate."""

    def _get_query_params(self, request: web.Request) -> Mapping[str, str]:
        """Get the query params to send upstream."""
        return {k: v for k, v in request.query.items() if k != "authSig"}

    def _get_config_entry_for_request(
        self, request: web.Request, frigate_instance_id: str | None = None
    ) -> ConfigEntry | None:
        """Get a ConfigEntry for a given request."""
        hass = request.app[KEY_HASS]

        if frigate_instance_id:
            return get_config_entry_for_frigate_instance_id(hass, frigate_instance_id)
        return get_default_config_entry(hass)

    def _get_fqdn_path(
        self, request: web.Request, path: str, frigate_instance_id: str | None = None
    ) -> str:
        """Get the fully qualified domain name path."""
        config_entry = self._get_config_entry_for_request(
            request, frigate_instance_id=frigate_instance_id
        )
        if not config_entry:
            raise HASSWebProxyLibNotFoundRequestError()
        return str(URL(config_entry.data[CONF_URL]) / path)

    async def _get_frigate_auth_for_request(
        self, request: web.Request, frigate_instance_id: str | None = None
    ) -> dict[str, str]:
        hass = request.app[KEY_HASS]
        client = None
        if frigate_instance_id:
            client = get_client_for_frigate_instance_id(
                hass, frigate_instance_id=frigate_instance_id
            )
        else:
            config_entry = self._get_config_entry_for_request(request)
            if config_entry:
                client = get_client_for_config_entry(hass, config_entry)

        if client is None:
            _LOGGER.warning("No Frigate client found for request '%s'. ", request.url)
            return {}
        return await client.get_auth_headers()

    # Override the get method to inject Frigate auth headers for authenticated requests.
    async def get(self, request: web.Request, **kwargs: Any) -> Any:
        auth_headers = await self._get_frigate_auth_for_request(
            request, kwargs.get("frigate_instance_id")
        )

        existing_headers = kwargs.get("headers", {})
        kwargs["headers"] = {**existing_headers, **auth_headers}

        # This mixin is only used with ProxyView or WebsocketProxyView, which define a `get` method, so we can safely ignore the check.
        return await super().get(request, **kwargs)  # type: ignore[misc]


class FrigateProxyView(FrigateProxyViewMixin, ProxyView):
    """A proxy for Frigate."""


class FrigateWebsocketProxyView(FrigateProxyViewMixin, WebsocketProxyView):
    """A websocket proxy for Frigate."""


class SnapshotsProxyView(FrigateProxyView):
    """A proxy for snapshots."""

    url = "/api/frigate/{frigate_instance_id:.+}/snapshot/{eventid:.*}"
    extra_urls = ["/api/frigate/snapshot/{eventid:.*}"]

    name = "api:frigate:snapshots"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"api/events/{kwargs['eventid']}/snapshot.jpg",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class RecordingProxyView(FrigateProxyView):
    """A proxy for recordings."""

    url = "/api/frigate/{frigate_instance_id:.+}/recording/{camera:.+}/start/{start:[.0-9]+}/end/{end:[.0-9]*}"
    extra_urls = [
        "/api/frigate/recording/{camera:.+}/start/{start:[.0-9]+}/end/{end:[.0-9]*}"
    ]

    name = "api:frigate:recording"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"api/{kwargs['camera']}/start/{kwargs['start']}"
                + f"/end/{kwargs['end']}/clip.mp4",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class ThumbnailsProxyView(FrigateProxyView):
    """A proxy for snapshots."""

    url = "/api/frigate/{frigate_instance_id:.+}/thumbnail/{eventid:.*}"

    name = "api:frigate:thumbnails"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"api/events/{kwargs['eventid']}/thumbnail.jpg",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class NotificationsProxyView(FrigateProxyView):
    """A proxy for notifications."""

    url = "/api/frigate/{frigate_instance_id:.+}/notifications/{event_id}/{path:.*}"
    extra_urls = ["/api/frigate/notifications/{event_id}/{path:.*}"]

    name = "api:frigate:notification"

    def _get_proxied_url(
        self,
        request: web.Request,
        **kwargs: Any,
    ) -> ProxiedURL:
        """Create proxied URL."""
        path: str = kwargs["path"]
        event_id: str = kwargs["event_id"]

        config_entry = self._get_config_entry_for_request(
            request, kwargs.get("frigate_instance_id")
        )
        if not config_entry:
            raise HASSWebProxyLibNotFoundRequestError("No Frigate instance found.")
        if not self._permit_request(request, config_entry, event_id=event_id):
            raise HASSWebProxyLibForbiddenRequestError("Request not permitted.")

        url_path: str | None = None
        if path == "thumbnail.jpg":
            url_path = f"api/events/{event_id}/thumbnail.jpg"
        elif path == "snapshot.jpg":
            url_path = f"api/events/{event_id}/snapshot.jpg"
        elif path.endswith("clip.mp4"):
            url_path = f"api/events/{event_id}/clip.mp4"
        elif path.endswith("event_preview.gif"):
            url_path = f"api/events/{event_id}/preview.gif"
        elif path.endswith("review_preview.gif"):
            url_path = f"api/review/{event_id}/preview"
        elif (
            path.endswith(".m3u8")
            or path.endswith(".ts")
            or path.endswith(".m4s")
            or path.endswith("init-v1-a1.mp4")
        ):
            # Proxy event HLS requests to the vod module
            file_name = os.path.basename(path)
            url_path = f"vod/event/{event_id}/{file_name}"

        if not url_path:
            raise HASSWebProxyLibNotFoundRequestError

        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                url_path,
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            allow_unauthenticated=True,
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )

    def _permit_request(
        self, request: web.Request, config_entry: ConfigEntry, event_id: str
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
            event_id_timestamp = int(event_id.partition(".")[0])
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
            _LOGGER.warning("The event id %s does not have a valid format.", event_id)
            return False


class VodProxyView(FrigateProxyView):
    """A proxy for vod playlists."""

    url = "/api/frigate/{frigate_instance_id:.+}/vod/{path:.+}/{manifest:.+}.m3u8"
    extra_urls = ["/api/frigate/vod/{path:.+}/{manifest:.+}.m3u8"]

    name = "api:frigate:vod:manifest"

    def _get_query_params(self, request: web.Request) -> Mapping[str, str]:
        """Get the query params to send upstream."""
        return request.query

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"vod/{kwargs['path']}/{kwargs['manifest']}.m3u8",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class VodSegmentProxyView(FrigateProxyView):
    """A proxy for vod segments."""

    url = "/api/frigate/{frigate_instance_id:.+}/vod/{path:.+}/{segment:.+}.{extension:(ts|m4s|mp4)}"
    extra_urls = ["/api/frigate/vod/{path:.+}/{segment:.+}.{extension:(ts|m4s|mp4)}"]

    name = "api:frigate:vod:segment"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        if not self._async_validate_signed_manifest(request):
            raise HASSWebProxyLibUnauthorizedRequestError()

        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"vod/{kwargs['path']}/{kwargs['segment']}.{kwargs['extension']}",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            allow_unauthenticated=True,
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )

    def _async_validate_signed_manifest(self, request: web.Request) -> bool:
        """Validate the signature for the manifest of this segment."""
        hass = request.app[KEY_HASS]
        secret = str(hass.data.get(DATA_SIGN_SECRET))
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


class JSMPEGProxyView(FrigateWebsocketProxyView):
    """A proxy for JSMPEG websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/jsmpeg/{path:.+}"
    extra_urls = ["/api/frigate/jsmpeg/{path:.+}"]

    name = "api:frigate:jsmpeg"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"live/jsmpeg/{kwargs['path']}",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class MSEProxyView(FrigateWebsocketProxyView):
    """A proxy for MSE websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/mse/{path:.+}"
    extra_urls = ["/api/frigate/mse/{path:.+}"]

    name = "api:frigate:mse"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"live/mse/{kwargs['path']}",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )


class WebRTCProxyView(FrigateWebsocketProxyView):
    """A proxy for WebRTC websocket."""

    url = "/api/frigate/{frigate_instance_id:.+}/webrtc/{path:.+}"
    extra_urls = ["/api/frigate/webrtc/{path:.+}"]

    name = "api:frigate:webrtc"

    def _get_proxied_url(self, request: web.Request, **kwargs: Any) -> ProxiedURL:
        """Create proxied URL."""
        return ProxiedURL(
            url=self._get_fqdn_path(
                request,
                f"live/webrtc/{kwargs['path']}",
                frigate_instance_id=kwargs.get("frigate_instance_id"),
            ),
            headers=kwargs["headers"],
            query_params=self._get_query_params(request),
        )
