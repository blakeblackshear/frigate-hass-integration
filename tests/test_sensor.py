"""Test the frigate sensors."""
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
    MS,
    NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import homeassistant.util.dt as dt_util

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
    TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
    TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
    TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
    TEST_SERVER_VERSION,
    TEST_STATS,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


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
async def test_object_count_icon(
    object_icon: tuple[str, str], hass: HomeAssistant
) -> None:
    """Test FrigateObjectCountSensor car icon."""
    object, icon = object_icon
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["objects"]["track"] = [object]
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(f"sensor.front_door_{object}")
    assert entity_state
    assert entity_state.attributes["icon"] == icon


@pytest.mark.parametrize(
    "camerazone_entities",
    [
        (
            "front_door",
            {
                TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
                TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
                TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
                TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
                TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
            },
        ),
        (
            "steps",
            {TEST_SENSOR_STEPS_PERSON_ENTITY_ID},
        ),
    ],
)
async def test_per_camerazone_device_info(
    camerazone_entities: Any, hass: HomeAssistant
) -> None:
    """Verify switch device information."""
    camerazone, entities = camerazone_entities
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{config_entry.entry_id}:{camerazone}")}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = {
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    }
    assert entities.issubset(entities_from_device)


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


async def test_per_entry_device_info(hass: HomeAssistant) -> None:
    """Verify switch device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, config_entry.entry_id)}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_SENSOR_DETECTION_FPS_ENTITY_ID in entities_from_device
    assert TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID in entities_from_device
    assert TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID in entities_from_device


async def test_detector_speed_sensor(hass: HomeAssistant) -> None:
    """Test DetectorSpeedSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "91"
    assert entity_state.attributes["icon"] == ICON_SPEEDOMETER
    assert entity_state.attributes["unit_of_measurement"] == MS

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["detectors"]["cpu1"]["inference_speed"] = 11.5
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "12"

    stats["detectors"]["cpu1"]["inference_speed"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["detectors"]["cpu1"]["inference_speed"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


async def test_camera_fps_sensor(hass: HomeAssistant) -> None:
    """Test CameraFpsSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "4"
    assert entity_state.attributes["icon"] == ICON_SPEEDOMETER
    assert entity_state.attributes["unit_of_measurement"] == FPS

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["front_door"]["camera_fps"] = 3.9
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "4"

    stats["front_door"]["camera_fps"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["front_door"]["camera_fps"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


@pytest.mark.parametrize(
    "entityid_to_uniqueid",
    [
        (
            TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person",
        ),
        (
            TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:detection",
        ),
        (
            TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_detector_speed:cpu1",
        ),
        (
            TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera",
        ),
        (
            TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_detection",
        ),
        (
            TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_process",
        ),
        (
            TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_skipped",
        ),
    ],
)
async def test_camera_unique_id(
    entityid_to_uniqueid: tuple[str, str], hass: HomeAssistant
) -> None:
    """Verify entity unique_id(s)."""
    entity_id, unique_id = entityid_to_uniqueid

    await setup_mock_frigate_config_entry(hass)

    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry
    assert registry_entry.unique_id == unique_id
