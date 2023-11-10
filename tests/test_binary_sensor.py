"""Test the frigate binary sensor."""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import DOMAIN, NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    TEST_BINARY_SENSOR_FRONT_DOOR_ALL_OCCUPANCY_ENTITY_ID,
    TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID,
    TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID,
    TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID,
    TEST_BINARY_SENSOR_STEPS_ALL_OCCUPANCY_ENTITY_ID,
    TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID,
    TEST_CONFIG_ENTRY_ID,
    TEST_SERVER_VERSION,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)


async def test_occupancy_binary_sensor_setup(hass: HomeAssistant) -> None:
    """Verify a successful occupancy binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "1")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert entity_state
    assert entity_state.state == "on"

    # Verify the steps (zone) motion sensor works.
    async_fire_mqtt_message(hass, "frigate/steps/person", "1")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "not_an_int")
    await hass.async_block_till_done()
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_audio_binary_sensor_setup(hass: HomeAssistant) -> None:
    """Verify a successful audio binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/audio/speech", "ON")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"

    async_fire_mqtt_message(hass, "frigate/front_door/audio/speech", "not_valid")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_motion_binary_sensor_setup(hass: HomeAssistant) -> None:
    """Verify a successful motion binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/motion", "ON")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"


async def test_binary_sensor_api_call_failed(hass: HomeAssistant) -> None:
    """Verify a failed API call results in unsuccessful setup."""
    client = create_mock_frigate_client()
    client.async_get_stats = AsyncMock(side_effect=FrigateApiClientError)
    await setup_mock_frigate_config_entry(hass, client=client)
    assert not hass.states.get(TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID)


@pytest.mark.parametrize(
    "camerazone_entity",
    [
        ("front_door", TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID),
        ("steps", TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID),
    ],
)
async def test_binary_sensor_device_info(
    camerazone_entity: Any, hass: HomeAssistant
) -> None:
    """Verify switch device information."""
    camerazone, entity = camerazone_entity
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{config_entry.entry_id}:{camerazone}")}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert entity in entities_from_device


async def test_binary_sensor_unique_id(hass: HomeAssistant) -> None:
    """Verify entity unique_id(s)."""
    await setup_mock_frigate_config_entry(hass)
    registry_entry = er.async_get(hass).async_get(
        TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID
    )
    assert registry_entry
    assert (
        registry_entry.unique_id
        == f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:front_door_person"
    )


async def test_binary_sensor_unload_will_unsubscribe(hass: HomeAssistant) -> None:
    """Verify entity unique_id(s)."""
    mock_unsubscribe = Mock()
    with patch(
        "custom_components.frigate.async_unsubscribe_topics", new=mock_unsubscribe
    ):
        config_entry = await setup_mock_frigate_config_entry(hass)
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
        mock_unsubscribe.assert_called()


async def test_binary_sensors_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)

    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={
            TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID,
            TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_FRONT_DOOR_ALL_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_STEPS_ALL_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID,
        },
        entities_visible={
            TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID,
            TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_FRONT_DOOR_ALL_OCCUPANCY_ENTITY_ID,
            TEST_BINARY_SENSOR_STEPS_ALL_OCCUPANCY_ENTITY_ID,
        },
    )
