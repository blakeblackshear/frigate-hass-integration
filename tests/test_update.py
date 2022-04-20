"""Test the frigate updaters."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.frigate import SCAN_INTERVAL
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from . import (
    TEST_STATS,
    TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


async def test_update_sensor_same_version(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["service"]["version"] = stats["service"]["latest_version"]
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.current_version == entity_state.latest_version
    assert entity_state.release_url


async def test_update_sensor_new_update(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.installed_version < entity_state.latest_version
    assert entity_state.release_url


async def test_update_sensor_bad_current(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["services"]["version"] = ""
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.installed_version is None


async def test_update_sensor_bad_latest(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["services"]["latest_version"] = "unknown"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.latest_version is None
    assert entity_state.release_url is None
