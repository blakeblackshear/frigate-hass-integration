"""Tests for the Frigate integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import web
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.frigate.const import DOMAIN
from homeassistant.config_entries import RELOAD_AFTER_UPDATE_DELAY, ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util

TEST_BINARY_SENSOR_FRONT_DOOR_MOTION_ENTITY_ID = "binary_sensor.front_door_motion"
TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_OCCUPANCY_ENTITY_ID = (
    "binary_sensor.front_door_person_occupancy"
)
TEST_BINARY_SENSOR_FRONT_DOOR_SPEECH_ENTITY_ID = "binary_sensor.front_door_speech_sound"
TEST_BINARY_SENSOR_FRONT_DOOR_ALL_OCCUPANCY_ENTITY_ID = (
    "binary_sensor.front_door_all_occupancy"
)
TEST_BINARY_SENSOR_STEPS_PERSON_OCCUPANCY_ENTITY_ID = (
    "binary_sensor.steps_person_occupancy"
)
TEST_BINARY_SENSOR_STEPS_ALL_OCCUPANCY_ENTITY_ID = "binary_sensor.steps_all_occupancy"
TEST_CAMERA_BIRDSEYE_ENTITY_ID = "camera.birdseye"
TEST_CAMERA_FRONT_DOOR_ENTITY_ID = "camera.front_door"

TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID = "image.front_door_person"

TEST_NUMBER_FRONT_DOOR_CONTOUR_AREA_ENTITY_ID = "number.front_door_contour_area"
TEST_NUMBER_FRONT_DOOR_THRESHOLD_ENTITY_ID = "number.front_door_threshold"

TEST_SWITCH_FRONT_DOOR_AUDIO_DETECT_ENTITY_ID = "switch.front_door_audio_detection"
TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID = "switch.front_door_detect"
TEST_SWITCH_FRONT_DOOR_MOTION_ENTITY_ID = "switch.front_door_motion"
TEST_SWITCH_FRONT_DOOR_SNAPSHOTS_ENTITY_ID = "switch.front_door_snapshots"
TEST_SWITCH_FRONT_DOOR_RECORDINGS_ENTITY_ID = "switch.front_door_recordings"
TEST_SWITCH_FRONT_DOOR_IMPROVE_CONTRAST_ENTITY_ID = "switch.front_door_improve_contrast"
TEST_SWITCH_FRONT_DOOR_PTZ_AUTOTRACKER_ENTITY_ID = "switch.front_door_ptz_autotracker"

TEST_SENSOR_CORAL_TEMPERATURE_ENTITY_ID = "sensor.frigate_apex_0_temperature"
TEST_SENSOR_GPU_LOAD_ENTITY_ID = "sensor.frigate_nvidia_geforce_rtx_3050_gpu_load"
TEST_SENSOR_STEPS_ALL_ENTITY_ID = "sensor.steps_all_count"
TEST_SENSOR_STEPS_PERSON_ENTITY_ID = "sensor.steps_person_count"
TEST_SENSOR_FRONT_DOOR_ALL_ENTITY_ID = "sensor.front_door_all_count"
TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID = "sensor.front_door_person_count"
TEST_SENSOR_DETECTION_FPS_ENTITY_ID = "sensor.frigate_detection_fps"
TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID = "sensor.frigate_cpu1_inference_speed"
TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID = "sensor.frigate_cpu2_inference_speed"
TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID = "sensor.front_door_camera_fps"
TEST_SENSOR_FRONT_DOOR_CAPTURE_CPU_USAGE = "sensor.front_door_capture_cpu_usage"
TEST_SENSOR_FRONT_DOOR_DETECT_CPU_USAGE = "sensor.front_door_detect_cpu_usage"
TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID = "sensor.front_door_detection_fps"
TEST_SENSOR_FRONT_DOOR_FFMPEG_CPU_USAGE = "sensor.front_door_ffmpeg_cpu_usage"
TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID = "sensor.front_door_process_fps"
TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID = "sensor.front_door_skipped_fps"
TEST_SENSOR_FRIGATE_STATUS_ENTITY_ID = "sensor.frigate_status"
TEST_UPDATE_FRIGATE_CONTAINER_ENTITY_ID = "update.frigate_server"

TEST_SERVER_VERSION = "0.13.0-0858859"
TEST_CONFIG_ENTRY_ID = "74565ad414754616000674c87bdc876c"
TEST_URL = "http://example.com"
TEST_FRIGATE_INSTANCE_ID = "frigate_client_id"
TEST_CONFIG = {
    "cameras": {
        "front_door": {
            "best_image_timeout": 60,
            "clips": {
                "enabled": True,
                "objects": None,
                "post_capture": 5,
                "pre_capture": 5,
                "required_zones": [],
                "retain": {"default": 10, "objects": {}},
            },
            "detect": {"enabled": True, "max_disappeared": 20},
            "audio": {
                "enabled": True,
                "max_not_heard": 30,
                "listen": ["bark", "speech"],
                "enabled_in_config": True,
            },
            "ffmpeg_cmds": [
                {
                    "cmd": "ffmpeg -hide_banner -loglevel warning -avoid_negative_ts make_zero -fflags +genpts+discardcorrupt -rtsp_transport tcp -stimeout 5000000 -use_wallclock_as_timestamps 1 -i rtsp://rtsp:password@cam-front-door/live -f segment -segment_time 10 -segment_format mp4 -reset_timestamps 1 -strftime 1 -c copy -an /tmp/cache/front_door-%Y%m%d%H%M%S.mp4 -c copy -f flv rtmp://127.0.0.1/live/front_door -r 4 -f rawvideo -pix_fmt yuv420p pipe:",
                    "roles": ["detect", "rtmp", "restream", "clips"],
                }
            ],
            "fps": 4,
            "frame_shape": [1080, 1920],
            "height": 1080,
            "motion": {
                "contour_area": 35,
                "delta_alpha": 0.2,
                "frame_alpha": 0.2,
                "frame_height": 180,
                "mask": None,
                "threshold": 25,
            },
            "mqtt": {
                "bounding_box": True,
                "crop": True,
                "enabled": True,
                "height": 270,
                "required_zones": [],
                "timestamp": True,
            },
            "name": "front_door",
            "objects": {
                "filters": {
                    "person": {
                        "mask": [],
                        "max_area": 24000000,
                        "min_area": 0,
                        "min_score": 0.6,
                        "threshold": 0.7,
                    }
                },
                "mask": None,
                "track": ["person"],
            },
            "onvif": {
                "autotracking": {
                    "enabled": True,
                    "enabled_in_config": True,
                },
            },
            "record": {"enabled": False, "retain_days": 30},
            "rtmp": {"enabled": True},
            "snapshots": {
                "bounding_box": False,
                "crop": False,
                "enabled": True,
                "height": None,
                "required_zones": [],
                "retain": {"default": 10, "objects": {}},
                "timestamp": False,
            },
            "width": 1920,
            "zones": {"steps": {}},
        },
    },
    "clips": {
        "max_seconds": 300,
        "retain": {"default": 10, "objects": {}},
        "tmpfs_cache_size": "",
    },
    "database": {"path": "/media/frigate/clips/frigate.db"},
    "detectors": {
        "cpu1": {"device": "usb", "num_threads": 3, "type": "cpu"},
    },
    "environment_vars": {},
    "logger": {"default": "INFO", "logs": {}},
    "model": {"height": 320, "width": 320},
    "mqtt": {
        "client_id": TEST_FRIGATE_INSTANCE_ID,
        "host": "mqtt",
        "port": 1883,
        "stats_interval": 60,
        "topic_prefix": "frigate",
        "user": None,
    },
    "snapshots": {"retain": {"default": 10, "objects": {}}},
    "go2rtc": {"streams": {"front_door": "rtsp://rtsp:password@cam-front-door/live"}},
}
TEST_STATS = {
    "cameras": {
        "front_door": {
            "camera_fps": 4.1,
            "capture_pid": 53,
            "detection_fps": 6.0,
            "pid": 52,
            "ffmpeg_pid": 54,
            "process_fps": 4.0,
            "skipped_fps": 0.0,
        },
    },
    "detection_fps": 13.7,
    "detectors": {
        "cpu1": {"detection_start": 0.0, "inference_speed": 91.43, "pid": 42},
        "cpu2": {"detection_start": 0.0, "inference_speed": 84.99, "pid": 44},
    },
    "service": {
        "storage": {
            "/dev/shm": {
                "free": 50.5,
                "mount_type": "tmpfs",
                "total": 67.1,
                "used": 16.6,
            },
            "/media/frigate/clips": {
                "free": 42429.9,
                "mount_type": "ext4",
                "total": 244529.7,
                "used": 189607.0,
            },
            "/media/frigate/recordings": {
                "free": 42429.9,
                "mount_type": "ext4",
                "total": 244529.7,
                "used": 189607.0,
            },
            "/tmp/cache": {
                "free": 976.8,
                "mount_type": "tmpfs",
                "total": 1000.0,
                "used": 23.2,
            },
        },
        "uptime": 101113,
        "version": "0.8.4-09a4d6d",
        "latest_version": "0.10.1",
        "temperatures": {"apex_0": 50.0},
    },
    "cpu_usages": {
        "52": {"cpu": 5.0, "mem": 1.0},
        "53": {"cpu": 3.0, "mem": 2.0},
        "54": {"cpu": 15.0, "mem": 4.0},
    },
    "gpu_usages": {
        "Nvidia GeForce RTX 3050": {
            "gpu": "19 %",
            "mem": "57.0 %",
        }
    },
    "processes": {
        "audioDetector": {"pid": 835},
        "go2rtc": {"pid": 89},
        "logger": {"pid": 727},
        "recording": {"pid": 729},
    },
}
TEST_EVENT_SUMMARY = [
    # Today
    {
        "camera": "front_door",
        "count": 51,
        "day": "2021-06-04",
        "label": "person",
        "zones": [],
    },
    {
        "camera": "front_door",
        "count": 52,
        "day": "2021-06-04",
        "label": "person",
        "zones": ["steps"],
    },
    # Yesterday
    {
        "camera": "front_door",
        "count": 53,
        "day": "2021-06-03",
        "label": "person",
        "zones": [],
    },
    # Other content from this month
    {
        "camera": "front_door",
        "count": 54,
        "day": "2021-06-02",
        "label": "person",
        "zones": [],
    },
    # Last month
    {
        "camera": "front_door",
        "count": 55,
        "day": "2021-05-01",
        "label": "person",
        "zones": [],
    },
    # Other content from this year
    {
        "camera": "front_door",
        "count": 56,
        "day": "2021-01-01",
        "label": "person",
        "zones": [],
    },
    # Empty camera
    {
        "camera": "empty_camera",
        "count": 0,
        "day": "2021-06-04",
        "label": "person",
        "zones": [],
    },
    # Empty label
    {
        "camera": "front_door",
        "count": 0,
        "day": "2021-06-04",
        "label": "car",
        "zones": [],
    },
    # Empty zone
    {
        "camera": "front_door",
        "count": 0,
        "day": "2021-06-04",
        "label": "person",
        "zones": ["empty"],
    },
]


async def start_frigate_server(
    aiohttp_server: Any, handlers: list[web.RouteDef]
) -> Any:
    """Start a fake Frigate server."""
    app = web.Application()
    app.add_routes(handlers)
    return await aiohttp_server(app)


def create_mock_frigate_client() -> AsyncMock:
    """Create mock frigate client."""
    mock_client = AsyncMock()
    mock_client.async_get_stats = AsyncMock(return_value=TEST_STATS)
    mock_client.async_get_config = AsyncMock(return_value=TEST_CONFIG)
    mock_client.async_get_event_summary = AsyncMock(return_value=TEST_EVENT_SUMMARY)
    mock_client.async_get_version = AsyncMock(return_value=TEST_SERVER_VERSION)
    return mock_client


def create_mock_frigate_config_entry(
    hass: HomeAssistant,
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    entry_id: str | None = TEST_CONFIG_ENTRY_ID,
    title: str | None = TEST_URL,
) -> ConfigEntry:
    """Add a test config entry."""
    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=entry_id,
        domain=DOMAIN,
        data=data or {CONF_URL: TEST_URL},
        title=title,
        options=options or {},
        version=2,
    )
    config_entry.add_to_hass(hass)
    return config_entry


async def setup_mock_frigate_config_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
    client: AsyncMock | None = None,
) -> ConfigEntry:
    """Add a mock Frigate config entry to hass."""
    config_entry = config_entry or create_mock_frigate_config_entry(hass)
    client = client or create_mock_frigate_client()

    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


async def verify_entities_are_setup_correctly_in_registry(
    hass: HomeAssistant,
    entities_enabled: set[str] | None = None,
    entities_disabled: set[str] | None = None,
    entities_visible: set[str] | None = None,
    entities_hidden: set[str] | None = None,
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    registry = er.async_get(hass)

    for entity in entities_enabled or {}:
        entry = registry.async_get(entity)
        assert entry
        assert not entry.disabled
        assert not entry.disabled_by

    for entity in entities_disabled or {}:
        entry = registry.async_get(entity)
        assert entry
        assert entry.disabled
        assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION

        entity_state = hass.states.get(entity)
        assert not entity_state

        # Update and test that entity is now enabled.
        updated_entry = registry.async_update_entity(entity, disabled_by=None)
        assert not updated_entry.disabled
        assert not updated_entry.disabled_by

    for entity in entities_visible or {}:
        entry = registry.async_get(entity)
        assert entry
        assert not entry.hidden
        assert not entry.hidden_by

    for entity in entities_hidden or {}:
        entry = registry.async_get(entity)
        assert entry
        assert entry.hidden
        assert entry.hidden_by == er.RegistryEntryHider.INTEGRATION

        # Update and test that entity is now visible.
        updated_entry = registry.async_update_entity(entity, hidden_by=None)
        assert not updated_entry.hidden
        assert not updated_entry.hidden_by


async def enable_and_load_entity(
    hass: HomeAssistant, client: AsyncMock, entity: str
) -> None:
    """Enable and load an entity."""

    # Keep the patch in place to ensure that coordinator updates that are
    # scheduled during the reload period will use the mocked API.
    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ):
        er.async_get(hass).async_update_entity(entity, disabled_by=None)
        await hass.async_block_till_done()
        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=RELOAD_AFTER_UPDATE_DELAY + 1),
        )
        await hass.async_block_till_done()
