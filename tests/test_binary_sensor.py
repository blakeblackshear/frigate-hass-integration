"""Test the frigate binary sensor."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import DOMAIN, NAME

from . import (
    TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID,
    TEST_BINARY_SENSOR_STEPS_PERSON_MOTION_ENTITY_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__package__)


async def test_binary_sensor_setup(hass: HomeAssistant) -> None:
    """Verify a successful binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "1")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"

    # Verify the steps (zone) motion sensor works.
    async_fire_mqtt_message(hass, "frigate/steps/person", "1")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_STEPS_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "not_an_int")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_binary_sensor_api_call_failed(hass: HomeAssistant) -> None:
    """Verify a failed API call results in unsuccessful setup."""
    client = create_mock_frigate_client()
    client.async_get_stats = AsyncMock(side_effect=Exception)
    await setup_mock_frigate_config_entry(hass, client=client)
    assert not hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID)
