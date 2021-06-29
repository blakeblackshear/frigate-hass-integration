"""Tests for the Frigate integration."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import web
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

TEST_BINARY_SENSOR_FRONT_DOOR_PERSON_MOTION_ENTITY_ID = (
    "binary_sensor.front_door_person_motion"
)
TEST_BINARY_SENSOR_STEPS_PERSON_MOTION_ENTITY_ID = "binary_sensor.steps_person_motion"
TEST_CAMERA_FRONT_DOOR_ENTITY_ID = "camera.front_door"
TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID = "camera.front_door_person"
TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID = "switch.front_door_detect"
TEST_SWITCH_FRONT_DOOR_SNAPSHOTS_ENTITY_ID = "switch.front_door_snapshots"
TEST_SWITCH_FRONT_DOOR_CLIPS_ENTITY_ID = "switch.front_door_clips"
TEST_SENSOR_STEPS_PERSON_ENTITY_ID = "sensor.steps_person"
TEST_SENSOR_FRONT_DOOR_PERSON_ENTITY_ID = "sensor.front_door_person"
TEST_SENSOR_DETECTION_FPS_ENTITY_ID = "sensor.detection_fps"
TEST_SENSOR_CPU1_INTFERENCE_SPEED_ENTITY_ID = "sensor.cpu1_inference_speed"
TEST_SENSOR_CPU2_INTFERENCE_SPEED_ENTITY_ID = "sensor.cpu2_inference_speed"
TEST_SENSOR_FRONT_DOOR_CAMERA_FPS_ENTITY_ID = "sensor.front_door_camera_fps"
TEST_SENSOR_FRONT_DOOR_DETECTION_FPS_ENTITY_ID = "sensor.front_door_detection_fps"
TEST_SENSOR_FRONT_DOOR_PROCESS_FPS_ENTITY_ID = "sensor.front_door_process_fps"
TEST_SENSOR_FRONT_DOOR_SKIPPED_FPS_ENTITY_ID = "sensor.front_door_skipped_fps"

TEST_SERVER_VERSION = "0.8.4-09a4d6d"
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
            "ffmpeg_cmds": [
                {
                    "cmd": "ffmpeg -hide_banner -loglevel warning -avoid_negative_ts make_zero -fflags +genpts+discardcorrupt -rtsp_transport tcp -stimeout 5000000 -use_wallclock_as_timestamps 1 -i rtsp://rtsp:password@cam-front-door/live -f segment -segment_time 10 -segment_format mp4 -reset_timestamps 1 -strftime 1 -c copy -an /tmp/cache/front_door-%Y%m%d%H%M%S.mp4 -c copy -f flv rtmp://127.0.0.1/live/front_door -r 4 -f rawvideo -pix_fmt yuv420p pipe:",
                    "roles": ["detect", "rtmp", "clips"],
                }
            ],
            "fps": 4,
            "frame_shape": [1080, 1920],
            "height": 1080,
            "motion": {
                "contour_area": 100,
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
}
TEST_STATS = {
    "detection_fps": 13.7,
    "detectors": {
        "cpu1": {"detection_start": 0.0, "inference_speed": 91.43, "pid": 42},
        "cpu2": {"detection_start": 0.0, "inference_speed": 84.99, "pid": 44},
    },
    "front_door": {
        "camera_fps": 4.1,
        "capture_pid": 53,
        "detection_fps": 6.0,
        "pid": 52,
        "process_fps": 4.0,
        "skipped_fps": 0.0,
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
    """Add a mock MotionEye config entry to hass."""
    config_entry = config_entry or create_mock_frigate_config_entry(hass)
    client = client or create_mock_frigate_client()

    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry
