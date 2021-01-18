import logging
import asyncio
import socket
from typing import Optional
import aiohttp
import async_timeout
import urllib.parse
from ipaddress import ip_address
from typing import Dict, Union

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


class FrigateApiClient:
    def __init__(
        self, host: str, session: aiohttp.ClientSession
    ) -> None:
        """API Client."""
        self._host = host
        self._session = session

    async def async_get_stats(self) -> dict:
        """Get data from the API."""
        url = urllib.parse.urljoin(self._host, "/api/stats")
        return await self.api_wrapper("get", url)

    async def async_get_events(self, camera=None, label=None, zone=None, after=None, before=None, limit: int = None) -> dict:
        """Get data from the API."""
        params = {"camera": camera, "label": label, "zone": zone, "after": after, "before": before, "limit": limit, "has_clip": 1}
        params = urllib.parse.urlencode({k: v for k, v in params.items() if not v is None and not v == ''})
        url = urllib.parse.urljoin(self._host, f"/api/events?{params}")
        return await self.api_wrapper("get", url)

    async def async_get_event_summary(self) -> dict:
        """Get data from the API."""
        params = {"has_clip": 1}
        params = urllib.parse.urlencode({k: v for k, v in params.items() if not v is None and not v == ''})
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
        self, method: str, url: str, data: dict = {}, headers: dict = {}
    ) -> dict:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(TIMEOUT, loop=asyncio.get_event_loop()):
                if method == "get":
                    response = await self._session.get(url, headers=headers, raise_for_status=True)
                    return await response.json()

                elif method == "put":
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
            _LOGGER.error("Something really wrong happend! - %s", exception)
            raise
