"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import (
    async_fire_mqtt_message,
    async_fire_time_changed,
)

from custom_components.frigate import SCAN_INTERVAL
from custom_components.frigate.const import (
    DOMAIN,
    FPS,
    ICON_CAR,
    ICON_CAT,
    ICON_DOG,
    ICON_OTHER,
    ICON_PERSON,
    ICON_SPEEDOMETER,
    NAME,
    VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import homeassistant.util.dt as dt_util

from . import (
    TEST_CONFIG,
    TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
    TEST_STATS,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__package__)


async def test_object_count_sensor(hass: HomeAssistant) -> None:
    """Test FrigateObjectCountSensor state."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "0"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "0"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "42")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "42"

    async_fire_mqtt_message(hass, "frigate/front_door/person", "NOT_AN_INT")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "42"


@pytest.mark.parametrize(
    "object_icon",
    [
        ("person", ICON_PERSON),
        ("car", ICON_CAR),
        ("dog", ICON_DOG),
        ("cat", ICON_CAT),
        ("SOMETHING_ELSE", ICON_OTHER),
    ],
)
async def test_object_count_icon(object_icon, hass: HomeAssistant) -> None:
    """Test FrigateObjectCountSensor car icon."""
    object, icon = object_icon
    config = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["objects"]["track"] = [object]
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)
    entity_state = hass.states.get(f"sensor.front_door_{object}")
    assert entity_state
    assert entity_state.attributes["icon"] == icon


@pytest.mark.parametrize(
    "camerazone_entity",
    [
        ("front_door", TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID),
        ("steps", TEST_SENSOR_STEPS_PERSON_ENTITY_ID),
    ],
)
async def test_object_count_device_info(
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
    assert device.model == VERSION

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert entity in entities_from_device


async def test_fps_sensor(hass: HomeAssistant) -> None:
    """Test FrigateFpsSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_SENSOR_DETECTION_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "14"
    assert entity_state.attributes["icon"] == ICON_SPEEDOMETER
    assert entity_state.attributes["unit_of_measurement"] == FPS

    stats = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["detection_fps"] = 41.9
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_DETECTION_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "42"

    stats["detection_fps"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_DETECTION_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["detection_fps"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_DETECTION_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


async def test_fps_sensor_device_info(hass: HomeAssistant) -> None:
    """Verify switch device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, config_entry.entry_id)}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model == VERSION

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_SENSOR_DETECTION_FPS_ENTITY_ID in entities_from_device
