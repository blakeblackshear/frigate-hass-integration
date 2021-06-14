"""Frigate API client."""
from __future__ import annotations

import asyncio
import logging
import socket
import urllib.parse

import aiohttp
import async_timeout

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}

# ==============================================================================
# Please do not add HomeAssistant specific imports/functionality to this module,
# so that this library can be optionally moved to a different repo at a later
# date.
# ==============================================================================


class FrigateApiClient:
    """Frigate API client."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Construct API Client."""
        self._host = host
        self._session = session

    async def async_get_stats(self) -> dict:
        """Get data from the API."""
        url = urllib.parse.urljoin(self._host, "/api/stats")
        return await self.api_wrapper("get", url)

    async def async_get_events(
        self,
        camera=None,
        label=None,
        zone=None,
        after=None,
        before=None,
        limit: int = None,
    ) -> dict:
        """Get data from the API."""
        params = {
            "camera": camera,
            "label": label,
            "zone": zone,
            "after": after,
            "before": before,
            "limit": limit,
            "has_clip": 1,
        }
        params = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""}
        )
        url = urllib.parse.urljoin(self._host, f"/api/events?{params}")
        return await self.api_wrapper("get", url)

    async def async_get_event_summary(self) -> dict:
        """Get data from the API."""
        params = urllib.parse.urlencode({"has_clip": 1})
        url = urllib.parse.urljoin(self._host, f"/api/events/summary?{params}")
        return await self.api_wrapper("get", url)

    async def async_get_config(self) -> dict:
        """Get data from the API."""
        url = urllib.parse.urljoin(self._host, "/api/config")
        return await self.api_wrapper("get", url)

    async def async_get_recordings_folder(self, path) -> dict:
        """Get data from the API."""
        url = urllib.parse.urljoin(self._host, f"/recordings/{path}/")
        return await self.api_wrapper("get", url)

    async def api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Get information from the API."""
        if data is None:
            data = {}
        if headers is None:
            headers = {}

        try:
            async with async_timeout.timeout(TIMEOUT, loop=asyncio.get_event_loop()):
                if method == "get":
                    response = await self._session.get(
                        url, headers=headers, raise_for_status=True
                    )
                    return await response.json()

                if method == "put":
                    await self._session.put(url, headers=headers, json=data)

                elif method == "patch":
                    await self._session.patch(url, headers=headers, json=data)

                elif method == "post":
                    await self._session.post(url, headers=headers, json=data)

        except asyncio.TimeoutError as exception:
            _LOGGER.error(
                "Timeout error fetching information from %s - %s",
                url,
                exception,
            )
            raise

        except (KeyError, TypeError) as exception:
            _LOGGER.error(
                "Error parsing information from %s - %s",
                url,
                exception,
            )
            raise
        except (aiohttp.ClientError, socket.gaierror) as exception:
            _LOGGER.error(
                "Error fetching information from %s - %s",
                url,
                exception,
            )
            raise
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error("Something really wrong happened! - %s", exception)
            raise
