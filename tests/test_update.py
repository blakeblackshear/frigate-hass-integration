"""Test the frigate updaters."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.frigate import SCAN_INTERVAL
from custom_components.frigate.const import FRIGATE_RELEASE_TAG_URL
from homeassistant.components.update.const import (
    ATTR_INSTALLED_VERSION,
    ATTR_LATEST_VERSION,
    ATTR_RELEASE_URL,
)
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from . import (
    TEST_STATS,
    TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)


async def test_update_sensor_new_update(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"
    assert (
        entity_state.attributes[ATTR_RELEASE_URL]
        == f"{FRIGATE_RELEASE_TAG_URL}/v0.10.1"
    )


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
    assert entity_state.state == "off"
    assert entity_state.attributes[ATTR_INSTALLED_VERSION] == "0.10.1"
    assert entity_state.attributes[ATTR_LATEST_VERSION] == "0.10.1"
    assert (
        entity_state.attributes[ATTR_RELEASE_URL]
        == f"{FRIGATE_RELEASE_TAG_URL}/v0.10.1"
    )


async def test_update_sensor_bad_current(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["service"]["version"] = ""
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"
    assert entity_state.attributes[ATTR_INSTALLED_VERSION] is None
    assert entity_state.attributes[ATTR_LATEST_VERSION] == "0.10.1"


async def test_update_sensor_bad_latest(hass: HomeAssistant) -> None:
    """Test FrigateUpdateSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["service"]["latest_version"] = "unknown"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"
    assert entity_state.attributes[ATTR_INSTALLED_VERSION] == "0.8.4"
    assert entity_state.attributes[ATTR_LATEST_VERSION] is None
    assert entity_state.attributes[ATTR_RELEASE_URL] is None


async def test_update_sensor_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)

    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID},
        entities_visible={TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID},
    )
