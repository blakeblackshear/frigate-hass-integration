"""Tests frigate diagnostics."""

from http import HTTPStatus
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import setup_mock_frigate_config_entry


async def _get_diagnostics_for_config_entry(
    hass: HomeAssistant, hass_client: Any, config_entry: ConfigEntry
) -> Any:
    """Return the diagnostics config entry for the specified domain."""
    assert await async_setup_component(hass, "diagnostics", {})

    client = await hass_client()
    response = await client.get(
        f"/api/diagnostics/config_entry/{config_entry.entry_id}"
    )
    assert response.status == HTTPStatus.OK
    return await response.json()


async def test_diagnostics(hass: HomeAssistant, hass_client: Any) -> None:
    """Test the diagnostics."""
    config_entry: ConfigEntry = await setup_mock_frigate_config_entry(hass)
    diagnostic_config: Dict[str, Any] = await _get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    )

    assert diagnostic_config["data"]["frigate_config"]
    assert diagnostic_config["data"]["frigate_stats"]
