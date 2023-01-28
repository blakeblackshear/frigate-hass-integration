"""Test the frigate number."""
from __future__ import annotations

import logging
from typing import Any

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import (
    TEST_CONFIG_ENTRY_ID,
    TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID,
    TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID,
    create_mock_frigate_client,
    enable_and_load_entity,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)

DISABLED_NUMBER_ENTITY_IDS = {
    TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID,
    TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID,
}


async def test_number_state(hass: HomeAssistant) -> None:
    """Verify a successful number setup."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    for entity_id in DISABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert not entity_state
        await enable_and_load_entity(hass, client, entity_id)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    for entity_id in DISABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state is not None

    async_fire_mqtt_message(hass, "frigate/front_door/motion_contour_area/state", "50")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "50.0"

    async_fire_mqtt_message(hass, "frigate/front_door/motion_threshold/state", "255")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "255.0"

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_bad_numbers(hass: HomeAssistant) -> None:
    """Verify bad state."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    for entity_id in DISABLED_NUMBER_ENTITY_IDS:
        await enable_and_load_entity(hass, client, entity_id)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    for entity_id in DISABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state is not None

    async_fire_mqtt_message(
        hass, "frigate/front_door/motion_contour_area/state", "NOT_A_NUMBER"
    )
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "35.0"

    async_fire_mqtt_message(
        hass, "frigate/front_door/motion_threshold/state", "NOT_A_NUMBER"
    )
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "25.0"


async def test_contour_area_set(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify setting a number."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(
        hass, client, TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID
    )

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID, "value": 35},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/motion_contour_area/set", "35", 0, False
    )


async def test_threshold_set(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify setting a number."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(
        hass, client, TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID
    )

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID, "value": 35},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/motion_threshold/set", "35", 0, False
    )


async def test_number_unique_id(hass: HomeAssistant) -> None:
    """Verify entity unique_id(s)."""
    await setup_mock_frigate_config_entry(hass)
    registry_entry = er.async_get(hass).async_get(
        TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID
    )
    assert registry_entry
    assert (
        registry_entry.unique_id
        == f"{TEST_CONFIG_ENTRY_ID}:number:front_door_contour_area"
    )
    registry_entry = er.async_get(hass).async_get(
        TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID
    )
    assert registry_entry
    assert (
        registry_entry.unique_id
        == f"{TEST_CONFIG_ENTRY_ID}:number:front_door_threshold"
    )


async def test_numbers_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)

    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_disabled=DISABLED_NUMBER_ENTITY_IDS,
    )
