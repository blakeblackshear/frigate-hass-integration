"""Frigate API client."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, cast

import aiohttp
import async_timeout
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

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Construct API Client."""
        self._host = host
        self._session = session

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

    async def api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
        decode_json: bool = True,
    ) -> Any:
        """Get information from the API."""
        if data is None:
            data = {}
        if headers is None:
            headers = {}

        try:
            async with async_timeout.timeout(TIMEOUT):
                func = getattr(self._session, method)
                if func:
                    response = await func(
                        url, headers=headers, raise_for_status=True, json=data
                    )
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
