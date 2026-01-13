"""Test the frigate sensors."""

from __future__ import annotations

import copy
import datetime
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    ICON_UPTIME,
    ICON_WAVEFORM,
)
from homeassistant.components.sensor import RestoreSensor
from homeassistant.const import PERCENTAGE, UnitOfSoundPressure, UnitOfTemperature
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
    TEST_SENSOR_FRIGATE_UPTIME_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_ALL_ACTIVE_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION,
    TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE,
    TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION,
    TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE,
    TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE,
    TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS,
    TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
    TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID,
    TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON,
    TEST_SENSOR_GLOBAL_CLASSIFICATION_RED_SHIRT,
    TEST_SENSOR_GLOBAL_FACE_BOB,
    TEST_SENSOR_GLOBAL_PLATE_ABC123,
    TEST_SENSOR_GPU_LOAD_ENTITY_ID,
    TEST_SENSOR_STEPS_ALL_ACTIVE_ENTITY_ID,
    TEST_SENSOR_STEPS_ALL_ENTITY_ID,
    TEST_SENSOR_STEPS_PERSON_ACTIVE_ENTITY_ID,
    TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
    TEST_SERVER_VERSION,
    TEST_STATS,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
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


async def test_active_object_count_sensor(hass: HomeAssistant) -> None:
    """Test FrigateActiveObjectCountSensor state."""
    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "0"

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "0"

    async_fire_mqtt_message(hass, "frigate/front_door/person/active", "42")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "42"

    async_fire_mqtt_message(hass, "frigate/front_door/person/active", "NOT_AN_INT")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
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
async def test_active_object_count_icon(
    object_icon: tuple[str, str], hass: HomeAssistant
) -> None:
    """Test FrigateObjectCountSensor car icon."""
    object_name, icon = object_icon
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["objects"]["track"] = [object_name]
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(f"sensor.front_door_{object_name}_active_count")
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
    assert device.model
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


async def test_uptime_sensor(hass: HomeAssistant) -> None:
    """Test FrigateUptimeSensor expected state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRIGATE_UPTIME_ENTITY_ID)

    entity_state = hass.states.get(TEST_SENSOR_FRIGATE_UPTIME_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "101113"
    assert entity_state.attributes["icon"] == ICON_UPTIME

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["service"]["uptime"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRIGATE_UPTIME_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["service"]["uptime"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRIGATE_UPTIME_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unknown"


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
    assert device.model
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


async def test_camera_audio_sensor(hass: HomeAssistant) -> None:
    """Test CameraAudioLevel state."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)
    await enable_and_load_entity(hass, client, TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
    assert entity_state
    assert entity_state.state == "-12"
    assert entity_state.attributes["icon"] == ICON_WAVEFORM
    assert entity_state.attributes["unit_of_measurement"] == UnitOfSoundPressure.DECIBEL

    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)

    stats["cameras"]["front_door"]["audio_dBFS"] = -3.9
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
    assert entity_state
    assert entity_state.state == "-4"

    stats["cameras"]["front_door"]["audio_dBFS"] = None
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
    assert entity_state
    assert entity_state.state == "unknown"

    stats["cameras"]["front_door"]["audio_dBFS"] = "NOT_A_NUMBER"
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
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
        (
            TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS,
            f"{TEST_CONFIG_ENTRY_ID}:sensor_review_status:front_door",
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
            TEST_SENSOR_FRONT_DOOR_ALL_ACTIVE_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID,
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
            TEST_SENSOR_STEPS_ALL_ACTIVE_ENTITY_ID,
            TEST_SENSOR_STEPS_PERSON_ENTITY_ID,
            TEST_SENSOR_STEPS_PERSON_ACTIVE_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_ALL_ACTIVE_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID,
            TEST_SENSOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID,
            TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID,
            TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID,
            TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID,
        },
    )


async def test_recognized_face_sensor(hass: HomeAssistant) -> None:
    """Test FrigateRecognizedFaceSensor state."""
    with patch(
        "custom_components.frigate.sensor.async_call_later"
    ) as mock_async_call_later:
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "Test"

        # Assert that async_call_later was called
        mock_async_call_later.assert_called_once()

        # test that other camera update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "not_front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "Test"

        # test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "Test"

        # test bad value
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            "something",
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "Test"

        # send good value
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        # Ensure that clearing the value works
        last_call_args, _ = mock_async_call_later.call_args_list[-1]
        callable_to_execute = last_call_args[2]
        callable_to_execute(datetime.datetime.now())
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_FACE)
        assert entity_state
        assert entity_state.state == "None"


async def test_recognized_plate_sensor(hass: HomeAssistant) -> None:
    """Test FrigateRecognizedPlateSensor state."""
    with patch(
        "custom_components.frigate.sensor.async_call_later"
    ) as mock_async_call_later:
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "Test"

        # Assert that async_call_later was called
        mock_async_call_later.assert_called_once()

        # test that other camera update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "not_front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "Test"

        # test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "test"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "Test"

        # test bad value
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            "something",
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "Test"

        # test that it falls back to plate
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "plate": "ABC123"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "ABC123"

        # Ensure that clearing the value works
        last_call_args, _ = mock_async_call_later.call_args_list[-1]
        callable_to_execute = last_call_args[2]
        callable_to_execute(datetime.datetime.now())
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_RECOGNIZED_PLATE)
        assert entity_state
        assert entity_state.state == "None"


async def test_classification_sensor(hass: HomeAssistant) -> None:
    """Test FrigateClassificationSensor state."""
    await setup_mock_frigate_config_entry(hass)

    # Check that classification sensor exists
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.state == "unavailable"

    # Make MQTT available
    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.state == "Unknown"

    # Send a classification update for color
    async_fire_mqtt_message(hass, "frigate/front_door/classification/color", "blue")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.state == "blue"

    # Update color again
    async_fire_mqtt_message(hass, "frigate/front_door/classification/color", "red")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.state == "red"

    # Send an empty payload - state should remain unchanged
    async_fire_mqtt_message(hass, "frigate/front_door/classification/color", "")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.state == "red"


async def test_classification_sensor_attributes(hass: HomeAssistant) -> None:
    """Test FrigateClassificationSensor attributes."""
    await setup_mock_frigate_config_entry(hass)
    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
    assert entity_state
    assert entity_state.name == "Front Door Color Classification"
    assert entity_state.attributes["icon"] == "mdi:tag-text"
    assert entity_state.attributes["friendly_name"] == "Front Door Color Classification"


async def test_classification_sensor_state_restoration(hass: HomeAssistant) -> None:
    """Test FrigateClassificationSensor restores valid state after restart."""
    mock_last_sensor_data = MagicMock()
    mock_last_sensor_data.native_value = "green"

    # Patch must be in place BEFORE setup so async_added_to_hass sees the mock
    with patch.object(
        RestoreSensor,
        "async_get_last_sensor_data",
        new_callable=AsyncMock,
        return_value=mock_last_sensor_data,
    ):
        await setup_mock_frigate_config_entry(hass)

        # Make MQTT available so entity becomes available
        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Verify state was restored to "green"
        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
        assert entity_state
        assert entity_state.state == "green"


async def test_classification_sensor_state_restoration_skips_invalid(
    hass: HomeAssistant,
) -> None:
    """Test FrigateClassificationSensor does not restore 'unknown' or 'unavailable'."""
    mock_last_sensor_data = MagicMock()
    mock_last_sensor_data.native_value = "unknown"

    with patch.object(
        RestoreSensor,
        "async_get_last_sensor_data",
        new_callable=AsyncMock,
        return_value=mock_last_sensor_data,
    ):
        await setup_mock_frigate_config_entry(hass)

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Should use default "Unknown" since "unknown" is not restored
        entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_COLOR_CLASSIFICATION)
        assert entity_state
        assert entity_state.state == "Unknown"


async def test_object_classification_sensor(hass: HomeAssistant) -> None:
    """Test FrigateObjectClassificationSensor state."""
    with patch(
        "custom_components.frigate.sensor.async_call_later"
    ) as mock_async_call_later:
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Test with sub_label
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "id": "1607123955.475377-mxklsc",
                    "camera": "front_door",
                    "timestamp": 1607123958.748393,
                    "model": "person_classifier",
                    "sub_label": "delivery_person",
                    "score": 0.87,
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Delivery Person"

        # Assert that async_call_later was called
        mock_async_call_later.assert_called_once()

        # Test that other camera update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "not_front_door",
                    "model": "person_classifier",
                    "sub_label": "test",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Delivery Person"

        # Test that other model update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "other_model",
                    "sub_label": "test",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Delivery Person"

        # Test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "face",
                    "camera": "front_door",
                    "model": "person_classifier",
                    "sub_label": "test",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Delivery Person"

        # Test with attribute instead of sub_label
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "id": "1607123955.475377-mxklsc",
                    "camera": "front_door",
                    "timestamp": 1607123958.748393,
                    "model": "person_classifier",
                    "attribute": "yes",
                    "score": 0.92,
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Yes"

        # Test bad value
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            "something",
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Yes"

        # Test message without sub_label or attribute
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "person_classifier",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "Yes"

        # Ensure that clearing the value works
        last_call_args, _ = mock_async_call_later.call_args_list[-1]
        callable_to_execute = last_call_args[2]
        callable_to_execute(datetime.datetime.now())
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
        )
        assert entity_state
        assert entity_state.state == "None"


async def test_object_classification_sensor_attributes(hass: HomeAssistant) -> None:
    """Test FrigateObjectClassificationSensor attributes."""
    await setup_mock_frigate_config_entry(hass)
    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(
        TEST_SENSOR_FRONT_DOOR_PERSON_CLASSIFIER_OBJECT_CLASSIFICATION
    )
    assert entity_state
    assert entity_state.name == "Front Door Person Classifier Object Classification"
    assert entity_state.attributes["icon"] == "mdi:tag-text"
    assert (
        entity_state.attributes["friendly_name"]
        == "Front Door Person Classifier Object Classification"
    )


async def test_review_status_sensor(hass: HomeAssistant) -> None:
    """Test FrigateReviewStatusSensor state."""
    await setup_mock_frigate_config_entry(hass)

    # Check that review status sensor exists
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.state == "unavailable"

    # Make MQTT available
    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    # Initial state should be unknown (None value)
    assert entity_state.state == "unknown"

    # Send NONE status
    async_fire_mqtt_message(hass, "frigate/front_door/review_status", "NONE")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.state == "NONE"

    # Send DETECTION status
    async_fire_mqtt_message(hass, "frigate/front_door/review_status", "DETECTION")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.state == "DETECTION"

    # Send ALERT status
    async_fire_mqtt_message(hass, "frigate/front_door/review_status", "ALERT")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.state == "ALERT"

    # Send NONE again
    async_fire_mqtt_message(hass, "frigate/front_door/review_status", "NONE")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.state == "NONE"


async def test_review_status_sensor_attributes(hass: HomeAssistant) -> None:
    """Test FrigateReviewStatusSensor attributes."""
    await setup_mock_frigate_config_entry(hass)
    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_REVIEW_STATUS)
    assert entity_state
    assert entity_state.name == "Front Door Review Status"
    assert entity_state.attributes["icon"] == "mdi:eye-check"
    assert entity_state.attributes["friendly_name"] == "Front Door Review Status"


async def test_global_face_sensor(hass: HomeAssistant) -> None:
    """Test FrigateGlobalFaceSensor state."""
    # Patch async_call_later to prevent timer interference from per-camera
    # FrigateRecognizedFaceSensor which creates timers that linger after test teardown
    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_FACE_BOB)
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Test face detection on front_door camera
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "bob"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_FACE_BOB)
        assert entity_state
        assert entity_state.state == "Front Door"

        # Test face detection on different camera
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "steps", "name": "bob"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_FACE_BOB)
        assert entity_state
        assert entity_state.state == "Steps"

        # Test that other face is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "alice"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_FACE_BOB)
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps

        # Test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "name": "bob"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_FACE_BOB)
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps


async def test_global_plate_sensor(hass: HomeAssistant) -> None:
    """Test FrigateGlobalPlateSensor state."""
    # Patch async_call_later to prevent timer interference from per-camera
    # FrigateRecognizedPlateSensor which creates timers that linger after test teardown
    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_PLATE_ABC123)
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Test plate detection on front_door camera
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "name": "ABC123"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_PLATE_ABC123)
        assert entity_state
        assert entity_state.state == "Front Door"

        # Test plate detection on different camera
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "steps", "name": "ABC123"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_PLATE_ABC123)
        assert entity_state
        assert entity_state.state == "Steps"

        # Test that other plate is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "lpr", "camera": "front_door", "name": "XYZ789"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_PLATE_ABC123)
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps

        # Test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps({"type": "face", "camera": "front_door", "name": "ABC123"}),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_PLATE_ABC123)
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps


async def test_global_object_classification_sensor(hass: HomeAssistant) -> None:
    """Test FrigateGlobalObjectClassificationSensor state."""
    # Patch async_call_later to prevent timer interference from per-camera
    # FrigateObjectClassificationSensor which creates timers that linger after test teardown
    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass)

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "unavailable"

        async_fire_mqtt_message(hass, "frigate/available", "online")
        await hass.async_block_till_done()

        # Test classification detection on front_door camera with sub_label
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "person_classifier",
                    "sub_label": "delivery_person",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "Front Door"

        # Test classification detection on different camera
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "steps",
                    "model": "person_classifier",
                    "sub_label": "delivery_person",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "Steps"

        # Test that other classification is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "person_classifier",
                    "sub_label": "red_shirt",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps

        # Test that other model update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "other_model",
                    "sub_label": "delivery_person",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps

        # Test that other type update is not picked up
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "face",
                    "camera": "front_door",
                    "model": "person_classifier",
                    "sub_label": "delivery_person",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(
            TEST_SENSOR_GLOBAL_CLASSIFICATION_DELIVERY_PERSON
        )
        assert entity_state
        assert entity_state.state == "Steps"  # Should still be Steps

        # Test with attribute instead of sub_label
        async_fire_mqtt_message(
            hass,
            "frigate/tracked_object_update",
            json.dumps(
                {
                    "type": "classification",
                    "camera": "front_door",
                    "model": "person_classifier",
                    "attribute": "red_shirt",
                }
            ),
        )
        await hass.async_block_till_done()

        entity_state = hass.states.get(TEST_SENSOR_GLOBAL_CLASSIFICATION_RED_SHIRT)
        assert entity_state
        assert entity_state.state == "Front Door"


async def test_global_face_sensor_api_error(hass: HomeAssistant) -> None:
    """Test that global face sensors handle API errors gracefully."""
    client = create_mock_frigate_client()
    # Make API call raise an error
    client.async_get_faces = AsyncMock(side_effect=Exception("API Error"))

    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass, client=client)

        # Verify no global face sensors were created due to API error
        registry = er.async_get(hass)
        unique_id = f"{TEST_CONFIG_ENTRY_ID}:sensor_global_face:bob"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is None


async def test_global_object_classification_sensor_api_error(
    hass: HomeAssistant,
) -> None:
    """Test that global object classification sensors handle API errors gracefully."""
    client = create_mock_frigate_client()
    # Make API call raise an error
    client.async_get_classification_model_classes = AsyncMock(
        side_effect=Exception("API Error")
    )

    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass, client=client)

        # Verify no global classification sensors were created due to API error
        registry = er.async_get(hass)
        unique_id = f"{TEST_CONFIG_ENTRY_ID}:sensor_global_object_classification:person_classifier_delivery_person"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is None


async def test_global_face_sensor_disabled_feature(hass: HomeAssistant) -> None:
    """Test that global face sensors are not created when face_recognition is disabled."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["face_recognition"]["enabled"] = False

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)

    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass, client=client)

        # Verify no global face sensors were created when feature is disabled
        registry = er.async_get(hass)
        unique_id = f"{TEST_CONFIG_ENTRY_ID}:sensor_global_face:bob"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is None


async def test_global_plate_sensor_disabled_feature(hass: HomeAssistant) -> None:
    """Test that global plate sensors are not created when lpr is disabled."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["lpr"]["enabled"] = False

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)

    with patch("custom_components.frigate.sensor.async_call_later"):
        await setup_mock_frigate_config_entry(hass, client=client)

        # Verify no global plate sensors were created when feature is disabled
        registry = er.async_get(hass)
        unique_id = f"{TEST_CONFIG_ENTRY_ID}:sensor_global_plate:abc123"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is None


async def test_lite_mode_filters_object_sensors(hass: HomeAssistant) -> None:
    """Test that lite mode only creates 'all' object sensors."""
    from custom_components.frigate.const import CONF_LITE_MODE

    # Create config entry with lite mode enabled
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_LITE_MODE: True}
    )
    await setup_mock_frigate_config_entry(hass, config_entry=config_entry)

    # Verify "all" sensors were created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID)
    assert entity_state is not None
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_ALL_ACTIVE_ENTITY_ID)
    assert entity_state is not None
    entity_state = hass.states.get(TEST_SENSOR_STEPS_ALL_ENTITY_ID)
    assert entity_state is not None
    entity_state = hass.states.get(TEST_SENSOR_STEPS_ALL_ACTIVE_ENTITY_ID)
    assert entity_state is not None

    # Verify individual object sensors were NOT created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state is None
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state is None
    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ENTITY_ID)
    assert entity_state is None
    entity_state = hass.states.get(TEST_SENSOR_STEPS_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state is None

    # Verify sound level sensor was NOT created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
    assert entity_state is None


async def test_normal_mode_creates_all_object_sensors(hass: HomeAssistant) -> None:
    """Test that normal mode (lite mode disabled) creates all object sensors."""
    from custom_components.frigate.const import CONF_LITE_MODE

    # Create config entry with lite mode explicitly disabled
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_LITE_MODE: False}
    )
    await setup_mock_frigate_config_entry(hass, config_entry=config_entry)

    # Verify "all" sensors were created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID)
    assert entity_state is not None
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_ALL_ACTIVE_ENTITY_ID)
    assert entity_state is not None

    # Verify individual object sensors WERE created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state is not None
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_PERSON_ACTIVE_ENTITY_ID)
    assert entity_state is not None

    # Verify sound level sensor WAS created
    entity_state = hass.states.get(TEST_SENSOR_FRONT_DOOR_SOUND_LEVEL_ID)
    assert entity_state is not None
