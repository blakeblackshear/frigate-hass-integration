"""Test the frigate select."""

from __future__ import annotations

import logging
from typing import Any

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import DOMAIN, NAME
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_SELECT_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_SELECT_PROFILE_ENTITY_ID,
    TEST_SERVER_VERSION,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


async def test_profile_select_state(hass: HomeAssistant) -> None:
    """Verify profile select setup and state changes."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    # Test setting profile to "home"
    async_fire_mqtt_message(hass, "frigate/profile/state", "home")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "home"

    # Test setting profile to "away"
    async_fire_mqtt_message(hass, "frigate/profile/state", "away")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "away"

    # Test invalid profile value is ignored
    async_fire_mqtt_message(hass, "frigate/profile/state", "invalid_profile")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "away"

    # Test bytes payload
    async_fire_mqtt_message(hass, "frigate/profile/state", b"home")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "home"

    # Test availability
    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_profile_select_option(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify selecting an option publishes to MQTT."""
    await setup_mock_frigate_config_entry(hass)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: TEST_SELECT_PROFILE_ENTITY_ID, "option": "away"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/profile/set", "away", 0, False
    )


async def test_profile_select_options(hass: HomeAssistant) -> None:
    """Verify the select entity has correct options."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.attributes["options"] == ["away", "home"]


async def test_profile_select_device_info(hass: HomeAssistant) -> None:
    """Verify select device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, config_entry.entry_id)}
    )
    assert device
    assert device.manufacturer == NAME

    assert device.model
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entity_registry = er.async_get(hass)
    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_SELECT_PROFILE_ENTITY_ID in entities_from_device


async def test_profile_select_unique_id(hass: HomeAssistant) -> None:
    """Verify entity unique_id."""
    await setup_mock_frigate_config_entry(hass)
    registry_entry = er.async_get(hass).async_get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert registry_entry
    assert registry_entry.unique_id == f"{TEST_CONFIG_ENTRY_ID}:select:profile"


async def test_profile_select_icon(hass: HomeAssistant) -> None:
    """Verify select icon."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state
    assert entity_state.attributes["icon"] == "mdi:home-account"


async def test_profile_select_not_created_without_profiles(
    hass: HomeAssistant,
) -> None:
    """Verify select entity is not created when no profiles configured."""
    client = create_mock_frigate_client()
    config = TEST_CONFIG.copy()
    config["profiles"] = {}
    client.async_get_config = lambda: config
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_SELECT_PROFILE_ENTITY_ID)
    assert entity_state is None
