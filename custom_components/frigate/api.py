"""Frigate API client."""

from __future__ import annotations

import asyncio
import datetime
import logging
import socket
from typing import Any, cast

import aiohttp
import async_timeout
from yarl import URL

from homeassistant.auth import jwt_wrapper

TIMEOUT = 10
REVIEW_SUMMARIZE_TIMEOUT = 60

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
        self,
        host: str,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        validate_ssl: bool = True,
    ) -> None:
        """Construct API Client."""
        self._host = host
        self._session = session
        self._username = username
        self._password = password
        self._token_data: dict[str, Any] = {}
        self.validate_ssl = validate_ssl

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

    async def async_get_event(
        self,
        event_id: str,
        decode_json: bool = True,
    ) -> dict[str, Any]:
        """Get a single event by ID from the API."""
        return cast(
            dict[str, Any],
            await self.api_wrapper(
                "get",
                str(URL(self._host) / f"api/events/{event_id}"),
                decode_json=decode_json,
            ),
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

    async def async_get_faces(self) -> list[str]:
        """Get list of known faces."""
        try:
            result = await self.api_wrapper(
                "get", str(URL(self._host) / "api/faces"), decode_json=True
            )

            if isinstance(result, dict):
                return [name for name in result.keys() if name != "train"]

            return []
        except FrigateApiClientError:
            return []

    async def async_get_classification_model_classes(
        self, model_name: str
    ) -> list[str]:
        """Get list of classification classes for a model."""
        try:
            result = await self.api_wrapper(
                "get",
                str(URL(self._host) / f"api/classification/{model_name}/dataset"),
                decode_json=True,
            )

            if isinstance(result, dict) and "categories" in result:
                categories = result["categories"]
                if isinstance(categories, dict):
                    return [name for name in categories.keys() if name != "none"]
            return []
        except FrigateApiClientError:
            return []

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
        name: str | None = None,
        decode_json: bool = True,
    ) -> dict[str, Any] | str:
        """Export recording."""
        result = await self.api_wrapper(
            "post",
            str(
                URL(self._host)
                / f"api/export/{camera}/start/{start_time}/end/{end_time}"
            ),
            data={"playback": playback_factor, "name": name},
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

    async def async_create_event(
        self,
        camera: str,
        label: str,
        sub_label: str = "",
        duration: int | None = 30,
        include_recording: bool = True,
    ) -> dict[str, Any]:
        """Create an event."""
        return cast(
            dict[str, Any],
            await self.api_wrapper(
                "post",
                str(URL(self._host) / f"api/events/{camera}/{label}/create"),
                data={
                    "sub_label": sub_label,
                    "duration": duration,
                    "include_recording": include_recording,
                },
            ),
        )

    async def async_end_event(self, event_id: str) -> dict[str, Any]:
        """End an event."""
        return cast(
            dict[str, Any],
            await self.api_wrapper(
                "put",
                str(URL(self._host) / f"api/events/{event_id}/end"),
            ),
        )

    async def async_review_summarize(
        self,
        start_time: float,
        end_time: float,
        decode_json: bool = True,
    ) -> dict[str, Any] | str:
        """Get review summary for a time period."""
        result = await self.api_wrapper(
            "post",
            str(
                URL(self._host)
                / f"api/review/summarize/start/{start_time}/end/{end_time}"
            ),
            decode_json=decode_json,
            timeout=REVIEW_SUMMARIZE_TIMEOUT,
        )
        return cast(dict[str, Any], result) if decode_json else result

    async def _get_token(self) -> None:
        """
        Obtain a new JWT token using the provided username and password.
        Sends a POST request to the login endpoint and extracts the token
        and expiration date from the response headers.
        """
        response = await self.api_wrapper(
            method="post",
            url=str(URL(self._host) / "api/login"),
            data={"user": self._username, "password": self._password},
            decode_json=False,
            is_login_request=True,
        )

        set_cookie_header = response.headers.get("Set-Cookie", "")
        if not set_cookie_header:
            raise KeyError("Missing Set-Cookie header in response")

        for cookie_prop in set_cookie_header.split(";"):
            cookie_prop = cookie_prop.strip()
            if cookie_prop.startswith("frigate_token="):
                jwt_token = cookie_prop.split("=", 1)[1]
                self._token_data["token"] = jwt_token
                try:
                    decoded_token = jwt_wrapper.unverified_hs256_token_decode(jwt_token)
                except Exception as e:
                    raise ValueError(f"Failed to decode JWT token: {e}")
                exp_timestamp = decoded_token.get("exp")
                if not exp_timestamp:
                    raise KeyError("JWT is missing 'exp' claim")
                self._token_data["expires"] = datetime.datetime.fromtimestamp(
                    exp_timestamp, datetime.UTC
                )
                break
        else:
            raise KeyError("Missing 'frigate_token' in Set-Cookie header")

    async def _refresh_token_if_needed(self) -> None:
        """
        Refresh the JWT token if it is expired or about to expire.
        """
        if "expires" not in self._token_data:
            await self._get_token()
            return

        current_time = datetime.datetime.now(datetime.UTC)
        if current_time >= self._token_data["expires"]:  # Compare UTC-aware datetimes
            await self._get_token()

    async def get_auth_headers(self) -> dict[str, str]:
        """
        Get headers for API requests, including the JWT token if available.
        Ensures that the token is refreshed if needed.
        """
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
        is_login_request: bool = False,
        timeout: int | None = None,
    ) -> Any:
        """Get information from the API."""
        if data is None:
            data = {}
        if headers is None:
            headers = {}

        if not is_login_request:
            headers.update(await self.get_auth_headers())

        try:
            timeout_value = timeout if timeout is not None else TIMEOUT
            async with async_timeout.timeout(timeout_value):
                func = getattr(self._session, method)
                if func:
                    response = await func(
                        url,
                        headers=headers,
                        raise_for_status=True,
                        json=data,
                        ssl=self.validate_ssl,
                    )
                    response.raise_for_status()
                    if is_login_request:
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
            if exc.status == 401:
                _LOGGER.error(
                    "Unauthorized (401) error for URL %s: %s", url, exc.message
                )
                raise FrigateApiClientError(
                    "Unauthorized access - check credentials."
                ) from exc
            elif exc.status == 403:
                _LOGGER.error("Forbidden (403) error for URL %s: %s", url, exc.message)
                raise FrigateApiClientError(
                    "Forbidden - insufficient permissions."
                ) from exc
            else:
                _LOGGER.error(
                    "Client response error (%d) for URL %s: %s",
                    exc.status,
                    url,
                    exc.message,
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
