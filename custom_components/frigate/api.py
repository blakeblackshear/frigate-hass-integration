"""Frigate API client."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, cast

import aiohttp
import async_timeout
import datetime
from yarl import URL

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__name__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}

# ==============================================================================
# Please do not add HomeAssistant specific imports/functionality to this module,
# so that this library can be optionally moved to a different repo at a later
# date.
# ==============================================================================


class FrigateApiClientError(Exception):
    """General FrigateApiClient error."""


class FrigateApiClient:
    """Frigate API client."""

    def __init__(
        self, host: str, session: aiohttp.ClientSession, username: str | None = None, password: str | None = None
    ) -> None:
        """Construct API Client."""
        self._host = host
        self._session = session
        self._username = username
        self._password = password
        self._token_data = {}

    async def async_get_version(self) -> str:
        """Get data from the API."""
        return cast(
            str,
            await self.api_wrapper(
                "get", str(URL(self._host) / "api/version"), decode_json=False
            ),
        )

    async def async_get_stats(self) -> dict[str, Any]:
        """Get data from the API."""
        return cast(
            dict[str, Any],
            await self.api_wrapper("get", str(URL(self._host) / "api/stats")),
        )

    async def async_get_events(
        self,
        cameras: list[str] | None = None,
        labels: list[str] | None = None,
        sub_labels: list[str] | None = None,
        zones: list[str] | None = None,
        after: int | None = None,
        before: int | None = None,
        limit: int | None = None,
        has_clip: bool | None = None,
        has_snapshot: bool | None = None,
        favorites: bool | None = None,
        decode_json: bool = True,
    ) -> list[dict[str, Any]]:
        """Get data from the API."""
        params = {
            "cameras": ",".join(cameras) if cameras else None,
            "labels": ",".join(labels) if labels else None,
            "sub_labels": ",".join(sub_labels) if sub_labels else None,
            "zones": ",".join(zones) if zones else None,
            "after": after,
            "before": before,
            "limit": limit,
            "has_clip": int(has_clip) if has_clip is not None else None,
            "has_snapshot": int(has_snapshot) if has_snapshot is not None else None,
            "include_thumbnails": 0,
            "favorites": int(favorites) if favorites is not None else None,
        }

        return cast(
            list[dict[str, Any]],
            await self.api_wrapper(
                "get",
                str(
                    URL(self._host)
                    / "api/events"
                    % {k: v for k, v in params.items() if v is not None}
                ),
                decode_json=decode_json,
            ),
        )

    async def async_get_event_summary(
        self,
        has_clip: bool | None = None,
        has_snapshot: bool | None = None,
        timezone: str | None = None,
        decode_json: bool = True,
    ) -> list[dict[str, Any]]:
        """Get data from the API."""
        params = {
            "has_clip": int(has_clip) if has_clip is not None else None,
            "has_snapshot": int(has_snapshot) if has_snapshot is not None else None,
            "timezone": str(timezone) if timezone is not None else None,
        }

        return cast(
            list[dict[str, Any]],
            await self.api_wrapper(
                "get",
                str(
                    URL(self._host)
                    / "api/events/summary"
                    % {k: v for k, v in params.items() if v is not None}
                ),
                decode_json=decode_json,
            ),
        )

    async def async_get_config(self) -> dict[str, Any]:
        """Get data from the API."""
        return cast(
            dict[str, Any],
            await self.api_wrapper("get", str(URL(self._host) / "api/config")),
        )

    async def async_get_ptz_info(
        self,
        camera: str,
        decode_json: bool = True,
    ) -> Any:
        """Get PTZ info."""
        return await self.api_wrapper(
            "get",
            str(URL(self._host) / "api" / camera / "ptz/info"),
            decode_json=decode_json,
        )

    async def async_get_path(self, path: str) -> Any:
        """Get data from the API."""
        return await self.api_wrapper("get", str(URL(self._host) / f"{path}/"))

    async def async_retain(
        self, event_id: str, retain: bool, decode_json: bool = True
    ) -> dict[str, Any] | str:
        """Un/Retain an event."""
        result = await self.api_wrapper(
            "post" if retain else "delete",
            str(URL(self._host) / f"api/events/{event_id}/retain"),
            decode_json=decode_json,
        )
        return cast(dict[str, Any], result) if decode_json else result

    async def async_export_recording(
        self,
        camera: str,
        playback_factor: str,
        start_time: float,
        end_time: float,
        decode_json: bool = True,
    ) -> dict[str, Any] | str:
        """Export recording."""
        result = await self.api_wrapper(
            "post",
            str(
                URL(self._host)
                / f"api/export/{camera}/start/{start_time}/end/{end_time}"
            ),
            data={"playback": playback_factor},
            decode_json=decode_json,
        )
        return cast(dict[str, Any], result) if decode_json else result

    async def async_get_recordings_summary(
        self, camera: str, timezone: str, decode_json: bool = True
    ) -> list[dict[str, Any]] | str:
        """Get recordings summary."""
        params = {"timezone": timezone}

        result = await self.api_wrapper(
            "get",
            str(
                URL(self._host)
                / f"api/{camera}/recordings/summary"
                % {k: v for k, v in params.items() if v is not None}
            ),
            decode_json=decode_json,
        )
        return cast(list[dict[str, Any]], result) if decode_json else result

    async def async_get_recordings(
        self,
        camera: str,
        after: int | None = None,
        before: int | None = None,
        decode_json: bool = True,
    ) -> dict[str, Any] | str:
        """Get recordings."""
        params = {
            "after": after,
            "before": before,
        }

        result = await self.api_wrapper(
            "get",
            str(
                URL(self._host)
                / f"api/{camera}/recordings"
                % {k: v for k, v in params.items() if v is not None}
            ),
            decode_json=decode_json,
        )
        return cast(dict[str, Any], result) if decode_json else result

    async def _get_token(self) -> None:
        """Obtain a new JWT token using the provided username and password."""
        response = await self.api_wrapper(
            "post",
            str(URL(self._host) / "api/login"),
            { "user": self._username, "password": self._password },
            decode_json=False,
            include_auth_headers=False,
            return_full_response=True,
        )

        for cookie_prop in response.headers.get("Set-Cookie", "").split(";"):
            if "frigate_token=" in cookie_prop:
                self._token_data["token"] = cookie_prop.split("=")[1]
            elif "expires=" in cookie_prop:
                self._token_data["expires"] = datetime.datetime.strptime(cookie_prop.split("=")[1].strip(), "%a, %d %b %Y %H:%M:%S %Z")

    async def _refresh_token_if_needed(self) -> None:
        """Refresh the JWT token if it is expired or about to expire."""
        if ("expires" not in self._token_data or datetime.datetime.now() >= self._token_data["expires"]):
            await self._get_token()

    async def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests, including JWT if available."""
        headers = {}

        if self._username and self._password:
            await self._refresh_token_if_needed()

            if "token" in self._token_data:
                headers["Authorization"] = f"Bearer {self._token_data['token']}"        
        
        return headers

    async def api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
        decode_json: bool = True,
        include_auth_headers: bool = True,
        return_full_response: bool = False,
    ) -> Any:
        """Get information from the API."""
        if data is None:
            data = {}

        default_headers = {}

        if include_auth_headers:
            default_headers.update(await self._get_headers())

        if headers is None:
            headers = default_headers
        else:
            headers.update(default_headers)

        _LOGGER.error(f"Sending request to {url} with headers: {headers}")

        try:
            async with async_timeout.timeout(TIMEOUT):
                func = getattr(self._session, method)
                if func:
                    response = await func(
                        url, headers=headers, raise_for_status=True, json=data
                    )

                    response.raise_for_status()

                    if return_full_response:
                        return response

                    if decode_json:
                        return await response.json()

                    return await response.text()

        except asyncio.TimeoutError as exc:
            _LOGGER.error(
                "Timeout error fetching information from %s: %s",
                url,
                exc,
            )
            raise FrigateApiClientError from exc

        except aiohttp.ClientResponseError as exc:
            # Handling errors like 401, 403, etc.
            _LOGGER.error(
                "Client response error while fetching information from %s: %s",
                url,
                exc,
            )
            raise FrigateApiClientError from exc

        except (KeyError, TypeError) as exc:
            _LOGGER.error(
                "Error parsing information from %s: %s",
                url,
                exc,
            )
            raise FrigateApiClientError from exc
        except (aiohttp.ClientError, socket.gaierror) as exc:
            _LOGGER.error(
                "Error fetching information from %s: %s",
                url,
                exc,
            )
            raise FrigateApiClientError from exc
