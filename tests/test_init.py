"""Test the frigate binary sensor."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import create_mock_frigate_client, setup_mock_frigate_config_entry

_LOGGER = logging.getLogger(__name__)


async def test_entry_unload(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""

    config_entry = await setup_mock_frigate_config_entry(hass)

    config_entries = hass.config_entries.async_entries(DOMAIN)
    assert len(config_entries) == 1
    assert config_entries[0] is config_entry
    assert config_entry.state == ConfigEntryState.LOADED

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.NOT_LOADED


async def test_entry_update(hass: HomeAssistant) -> None:
    """Test updating a config entry."""

    client = create_mock_frigate_client()
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    assert client.async_get_config.call_count == 1

    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ), patch(
        "custom_components.frigate.media_source.FrigateApiClient", return_value=client
    ):
        assert hass.config_entries.async_update_entry(
            entry=config_entry, title="new title"
        )
        await hass.async_block_till_done()

    # Entry will have been reloaded, and config will be re-fetched.
    assert client.async_get_config.call_count == 2


async def test_entry_async_get_config_fail(hass: HomeAssistant) -> None:
    """Test updating a config entry."""

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(side_effect=FrigateApiClientError)

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    assert config_entry.state == ConfigEntryState.SETUP_RETRY
