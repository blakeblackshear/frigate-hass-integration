"""Test the frigate number."""
from __future__ import annotations

import logging
from typing import Any

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from homeassistant.components.number import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import (
    TEST_CONFIG_ENTRY_ID,
    TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID,
    TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID,
    TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID,
    setup_mock_frigate_config_entry,
    test_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)

ENABLED_NUMBER_ENTITY_IDS = {}

DISABLED_NUMBER_ENTITY_IDS = {
    TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID,
    TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID,
}


async def test_number_state(hass: HomeAssistant) -> None:
    """Verify a successful binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    for entity_id in ENABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state == "unavailable"

    for entity_id in DISABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert not entity_state

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    for entity_id in ENABLED_NUMBER_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state is int

    async_fire_mqtt_message(hass, "frigate/front_door/contour_area/state", 50)
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID)
    assert entity_state
    assert entity_state.state == 50

    async_fire_mqtt_message(hass, "frigate/front_door/threshold/state", 255)
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID)
    assert entity_state
    assert entity_state.state == 255

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_number_set_value(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify turning a number on."""
    await setup_mock_frigate_config_entry(hass)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/detect/set", "ON", 0, False
    )


async def test_number_turn_off(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify turning a number off."""
    await setup_mock_frigate_config_entry(hass)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/detect/set", "OFF", 0, False
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


async def test_numberes_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)

    await test_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled=ENABLED_NUMBER_ENTITY_IDS,
        entities_disabled=DISABLED_NUMBER_ENTITY_IDS,
        entities_visible={
            TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID,
            TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID,
        },
    )
