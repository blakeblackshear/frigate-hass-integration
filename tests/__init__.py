"""Tests for the Frigate integration."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate.const import DOMAIN, NAME

TEST_CONFIG_ENTRY_ID = "74565ad414754616000674c87bdc876c"
TEST_HOST = "http://example.com"


def create_mock_frigate_client() -> AsyncMock:
    """Create mock frigate client."""
    mock_client = AsyncMock()
    mock_client.async_get_stats = AsyncMock(return_value={})
    return mock_client


def create_mock_frigate_config_entry(
    hass: HomeAssistant,
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> ConfigEntry:
    """Add a test config entry."""
    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data=data or {CONF_HOST: TEST_HOST},
        title=NAME,
        options=options or {},
    )
    config_entry.add_to_hass(hass)
    return config_entry
