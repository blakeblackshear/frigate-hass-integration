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
from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import DOMAIN, FPS, MS, NAME
from custom_components.frigate.icons import (
    ICON_BICYCLE,
    ICON_CAR,
    ICON_CAT,
    ICON_CORAL,
    ICON_COW,
    ICON_DOG,
    ICON_HORSE,
    ICON_MOTORCYCLE,
    ICON_OTHER,
    ICON_PERSON,
    ICON_SERVER,
    ICON_SPEEDOMETER,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import homeassistant.util.dt as dt_util

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID,
    TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
    TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
    TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
    TEST_SENSOR_GPU_LOAD_ENTITY_ID,
    TEST_SENSOR_STEPS_ALL_ENTITY_ID,
    TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
    TEST_SERVER_VERSION,
    TEST_STATS,
    create_mock_frigate_client,
    enable_and_load_entity,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
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
        ("motorcycle", ICON_MOTORCYCLE),
        ("bicycle", ICON_BICYCLE),
        ("cow", ICON_COW),
        ("horse", ICON_HORSE),
        ("SOMETHING_ELSE", ICON_OTHER),
    ],
)
async def test_object_count_icon(
    object_icon: tuple[str, str], hass: HomeAssistant
) -> None:
    """Test FrigateObjectCountSensor car icon."""
    object_name, icon = object_icon
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["objects"]["track"] = [object_name]
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(f"sensor.front_door_{object_name}_count")
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
            {
                TEST_SENSOR_STEPS_ALL_ENTITY_ID,
                TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
            },
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

    for entity in entities:
        entity_registry.async_update_entity(entity, disabled_by=None)

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
    await enable_and_load_entity(hass, client, TEST_SENSOR_DETECTION_FPS_ENTITY_ID)

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


async def test_coral_temp_sensor(hass: HomeAssistant) -> None:
    """Test CoralTempSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID)

    entity_state = hass.states.get(TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "50.0"
    assert entity_state.attributes["icon"] == ICON_CORAL
    assert entity_state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["service"]["temperatures"]["apex_0"] = 41.9
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "41.9"

    stats["service"]["temperatures"]["apex_0"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["service"]["temperatures"]["apex_0"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


async def test_status_sensor_success(hass: HomeAssistant) -> None:
    """Test FrigateStatusSensor expected state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID)

    entity_state = hass.states.get(TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "running"
    assert entity_state.attributes["icon"] == ICON_SERVER


async def test_status_sensor_error(hass: HomeAssistant) -> None:
    """Test FrigateStatusSensor unexpected state."""

    client: AsyncMock = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    client.async_get_stats = AsyncMock(side_effect=FrigateApiClientError)
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID)
    assert entity_state

    # The update coordinator will treat the error as unavailability.
    assert entity_state.state == "unavailable"
    assert entity_state.attributes["icon"] == ICON_SERVER


async def test_per_entry_device_info(hass: HomeAssistant) -> None:
    """Verify switch device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    entities = {
        TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
        TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
        TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
    }
    for entity in entities:
        entity_registry.async_update_entity(entity, disabled_by=None)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, config_entry.entry_id)}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = {
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    }
    assert entities.issubset(entities_from_device)


async def test_detector_speed_sensor(hass: HomeAssistant) -> None:
    """Test DetectorSpeedSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(
        hass, client, TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID
    )

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
    await enable_and_load_entity(
        hass, client, TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID
    )

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "4"
    assert entity_state.attributes["icon"] == ICON_SPEEDOMETER
    assert entity_state.attributes["unit_of_measurement"] == FPS

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["cameras"]["front_door"]["camera_fps"] = 3.9
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "4"

    stats["cameras"]["front_door"]["camera_fps"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["cameras"]["front_door"]["camera_fps"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


async def test_camera_cpu_usage_sensor(hass: HomeAssistant) -> None:
    """Test CameraProcessCpuSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE)

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "3.0"
    assert entity_state.attributes["icon"] == ICON_CORAL
    assert entity_state.attributes["unit_of_measurement"] == PERCENTAGE

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "5.0"
    assert entity_state.attributes["icon"] == ICON_CORAL
    assert entity_state.attributes["unit_of_measurement"] == PERCENTAGE

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "15.0"
    assert entity_state.attributes["icon"] == ICON_CORAL
    assert entity_state.attributes["unit_of_measurement"] == PERCENTAGE

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["cpu_usages"]["52"] = {"cpu": None, "mem": None}
    stats["cpu_usages"]["53"] = {"cpu": None, "mem": None}
    stats["cpu_usages"]["54"] = {"cpu": None, "mem": None}
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "unknown"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "unknown"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE)
    assert entity_state
    assert entity_state.state == "unknown"


async def test_gpu_usage_sensor(hass: HomeAssistant) -> None:
    """Test CameraProcessCpuSensor state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_GPU_LOAD_ENTITY_ID)

    entity_state = hass.states.get(TEST_SENSOR_GPU_LOAD_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "19.0"
    assert entity_state.attributes["icon"] == ICON_SPEEDOMETER
    assert entity_state.attributes["unit_of_measurement"] == PERCENTAGE

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["gpu_usages"]["Nvidia GeForce RTX 3050"] = {"gpu": -1, "mem": -1}
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_GPU_LOAD_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["gpu_usages"]["Nvidia GeForce RTX 3050"] = {
        "gpu": "not a number",
        "mem": "not a number",
    }
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_GPU_LOAD_ENTITY_ID)
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


async def test_sensors_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)
    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={
            TEST_SENSOR_STEPS_ALL_ENTITY_ID,
            TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
        },
        entities_disabled={
            TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE,
            TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE,
            TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE,
            TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
            TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
            TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
        },
        entities_visible={
            TEST_SENSOR_STEPS_ALL_ENTITY_ID,
            TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
            TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
            TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
            TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
        },
    )
