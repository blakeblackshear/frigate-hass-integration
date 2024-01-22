"""Test the frigate camera."""
from __future__ import annotations

import copy
import datetime
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
    ATTR_END_TIME,
    ATTR_EVENT_ID,
    ATTR_FAVORITE,
    ATTR_PLAYBACK_FACTOR,
    ATTR_PTZ_ACTION,
    ATTR_PTZ_ARGUMENT,
    ATTR_START_TIME,
    CONF_ENABLE_WEBRTC,
    CONF_RTMP_URL_TEMPLATE,
    CONF_RTSP_URL_TEMPLATE,
    DOMAIN,
    NAME,
    SERVICE_EXPORT_RECORDING,
    SERVICE_FAVORITE_EVENT,
    SERVICE_PTZ,
)
from homeassistant.components.camera import (
    DOMAIN as CAMERA_DOMAIN,
    SERVICE_DISABLE_MOTION,
    SERVICE_ENABLE_MOTION,
    StreamType,
    async_get_image,
    async_get_stream_source,
)
from homeassistant.components.websocket_api.const import TYPE_RESULT
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import homeassistant.util.dt as dt_util

from . import (
    TEST_CAMERA_BIRDSEYE_ENTITY_ID,
    TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_FRIGATE_INSTANCE_ID,
    TEST_SERVER_VERSION,
    TEST_STATS,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)


async def test_frigate_camera_setup_rtsp(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up a camera."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"
    assert entity_state.attributes["supported_features"] == 2
    assert entity_state.attributes["restream_type"] == "rtsp"
    assert entity_state.attributes["frontend_stream_type"] == StreamType.HLS

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtsp://example.com:8554/front_door"

    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg?h=277",
        content=b"data-277",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID, height=277)
    assert image
    assert image.content == b"data-277"


async def test_frigate_camera_setup_web_rtc(
    hass: HomeAssistant,
    aioclient_mock: Any,
    hass_ws_client: Any,
) -> None:
    """Set up a camera."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_ENABLE_WEBRTC: True}
    )

    await setup_mock_frigate_config_entry(
        hass, client=client, config_entry=config_entry
    )

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"
    assert entity_state.attributes["supported_features"] == 2
    assert entity_state.attributes["restream_type"] == "webrtc"
    assert entity_state.attributes["frontend_stream_type"] == StreamType.WEB_RTC

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source == "rtsp://example.com:8554/front_door"

    aioclient_mock.post(
        "http://example.com/api/go2rtc/webrtc?src=front_door",
        json={"type": "answer", "sdp": "return_sdp"},
    )
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 5,
            "type": "camera/web_rtc_offer",
            "entity_id": TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            "offer": "send_sdp",
        }
    )

    msg = await client.receive_json()
    assert msg["id"] == 5
    assert msg["type"] == TYPE_RESULT
    assert msg["success"]
    assert msg["result"]["answer"] == "return_sdp"


async def test_frigate_camera_setup_birdseye_rtsp(hass: HomeAssistant) -> None:
    """Set up birdseye camera."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["birdseye"] = {"restream": True}
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_BIRDSEYE_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"

    source = await async_get_stream_source(hass, TEST_CAMERA_BIRDSEYE_ENTITY_ID)
    assert source
    assert source == "rtsp://example.com:8554/birdseye"


async def test_frigate_camera_setup_rtmp(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up a camera."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["go2rtc"] = {}
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"
    assert entity_state.attributes["supported_features"] == 2
    assert entity_state.attributes["restream_type"] == "rtmp"

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtmp://example.com/live/front_door"

    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg?h=277",
        content=b"data-277",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID, height=277)
    assert image
    assert image.content == b"data-277"


async def test_frigate_extra_attributes(hass: HomeAssistant) -> None:
    """Test that frigate extra attributes are correct."""
    await setup_mock_frigate_config_entry(hass)
    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.attributes["camera_name"] == "front_door"
    assert entity_state.attributes["client_id"] == TEST_FRIGATE_INSTANCE_ID


async def test_frigate_camera_image_height(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Ensure async_camera_image respects height parameter."""

    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg?h=1000",
        content=b"data-1000",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID, height=1000)
    assert image
    assert image.content == b"data-1000"

    # Don't specify the height (no argument should be passed).
    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg",
        content=b"data-no-height",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert image
    assert image.content == b"data-no-height"


async def test_frigate_camera_birdseye_image_height(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Ensure async_camera_image respects height parameter."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["birdseye"] = {"restream": True}
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    aioclient_mock.get(
        "http://example.com/api/birdseye/latest.jpg?h=1000",
        content=b"data-1000",
    )

    image = await async_get_image(hass, TEST_CAMERA_BIRDSEYE_ENTITY_ID, height=1000)
    assert image
    assert image.content == b"data-1000"

    # Don't specify the height (no argument should be passed).
    aioclient_mock.get(
        "http://example.com/api/birdseye/latest.jpg",
        content=b"data-no-height",
    )

    image = await async_get_image(hass, TEST_CAMERA_BIRDSEYE_ENTITY_ID)
    assert image
    assert image.content == b"data-no-height"


async def test_frigate_camera_setup_no_stream(hass: HomeAssistant) -> None:
    """Set up a camera without streaming."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["go2rtc"] = {}
    config["cameras"]["front_door"]["rtmp"]["enabled"] = False
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "idle"
    assert not entity_state.attributes["supported_features"]
    assert entity_state.attributes["restream_type"] == "none"

    assert not await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)


async def test_frigate_camera_recording_camera_state(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up an mqtt camera."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["go2rtc"] = {}
    config["cameras"]["front_door"]["rtmp"]["enabled"] = False
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "idle"
    assert not entity_state.attributes["supported_features"]

    async_fire_mqtt_message(hass, "frigate/front_door/recordings/state", "ON")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "recording"
    assert entity_state.attributes["supported_features"] == 0


async def test_camera_device_info(hass: HomeAssistant) -> None:
    """Verify camera device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{config_entry.entry_id}:front_door")}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_CAMERA_FRONT_DOOR_ENTITY_ID in entities_from_device


async def test_camera_enable_motion_detection(
    hass: HomeAssistant, mqtt_mock: Any
) -> None:
    """Test built in motion detection."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"
    assert entity_state.attributes["supported_features"] == 2

    async_fire_mqtt_message(hass, "frigate/front_door/motion/state", "ON")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state

    await hass.services.async_call(
        CAMERA_DOMAIN,
        SERVICE_ENABLE_MOTION,
        {ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/motion/set", "ON", 0, False
    )


async def test_camera_disable_motion_detection(
    hass: HomeAssistant, mqtt_mock: Any
) -> None:
    """Test built in motion detection."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"
    assert entity_state.attributes["supported_features"] == 2

    async_fire_mqtt_message(hass, "frigate/front_door/motion/state", "OFF")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state

    await hass.services.async_call(
        CAMERA_DOMAIN,
        SERVICE_DISABLE_MOTION,
        {ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/motion/set", "OFF", 0, False
    )


async def test_camera_unavailable(hass: HomeAssistant) -> None:
    """Test that camera is marked as unavailable."""
    client = create_mock_frigate_client()
    stats: dict[str, Any] = copy.deepcopy(TEST_STATS)
    client.async_get_stats = AsyncMock(return_value=stats)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "streaming"

    stats["cameras"]["front_door"]["camera_fps"] = 0.0

    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


@pytest.mark.parametrize(
    "entityid_to_uniqueid",
    [
        (TEST_CAMERA_FRONT_DOOR_ENTITY_ID, f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
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


async def test_camera_option_rtsp_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify camera with the RTSP URL template option."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_RTSP_URL_TEMPLATE: ("rtsp://localhost/{{ name }}")}
    )

    await setup_mock_frigate_config_entry(
        hass, client=client, config_entry=config_entry
    )

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtsp://localhost/front_door"


async def test_birdseye_option_rtsp_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify birdseye cam with the RTSP URL template option."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["birdseye"] = {"restream": True}
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_RTSP_URL_TEMPLATE: ("rtsp://localhost/{{ name }}")}
    )

    await setup_mock_frigate_config_entry(
        hass, client=client, config_entry=config_entry
    )

    source = await async_get_stream_source(hass, TEST_CAMERA_BIRDSEYE_ENTITY_ID)
    assert source
    assert source == "rtsp://localhost/birdseye"


async def test_camera_option_rtmp_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify camera with the RTMP URL template option."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["go2rtc"] = {}
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_RTMP_URL_TEMPLATE: ("rtmp://localhost/{{ name }}")}
    )

    await setup_mock_frigate_config_entry(
        hass, client=client, config_entry=config_entry
    )

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtmp://localhost/front_door"


async def test_cameras_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)
    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={
            TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
        },
        entities_visible={
            TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
        },
    )


async def test_export_recording_service_call(
    hass: HomeAssistant,
) -> None:
    """Test export recording service call."""
    post_success = {"success": True, "message": "Post success"}

    client = create_mock_frigate_client()
    client.async_export_recording = AsyncMock(return_value=post_success)
    await setup_mock_frigate_config_entry(hass, client=client)

    playback_factor = "Realtime"
    start_time = "2023-09-23 13:33:44"
    end_time = "2023-09-23 18:11:22"
    await hass.services.async_call(
        DOMAIN,
        SERVICE_EXPORT_RECORDING,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_PLAYBACK_FACTOR: playback_factor,
            ATTR_START_TIME: start_time,
            ATTR_END_TIME: end_time,
        },
        blocking=True,
    )
    client.async_export_recording.assert_called_with(
        "front_door",
        playback_factor,
        datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp(),
        datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp(),
    )


async def test_retain_service_call(
    hass: HomeAssistant,
) -> None:
    """Test retain service call."""
    post_success = {"success": True, "message": "Post success"}

    client = create_mock_frigate_client()
    client.async_retain = AsyncMock(return_value=post_success)
    await setup_mock_frigate_config_entry(hass, client=client)

    event_id = "1656282822.206673-bovnfg"
    await hass.services.async_call(
        DOMAIN,
        SERVICE_FAVORITE_EVENT,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_EVENT_ID: event_id,
            ATTR_FAVORITE: True,
        },
        blocking=True,
    )
    client.async_retain.assert_called_with(event_id, True)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_FAVORITE_EVENT,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_EVENT_ID: event_id,
            ATTR_FAVORITE: False,
        },
        blocking=True,
    )
    client.async_retain.assert_called_with(event_id, False)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_FAVORITE_EVENT,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_EVENT_ID: event_id,
        },
        blocking=True,
    )
    client.async_retain.assert_called_with(event_id, True)


async def test_ptz_move_service_call(
    hass: HomeAssistant,
    mqtt_mock: Any,
) -> None:
    """Test ptz service call."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PTZ,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_PTZ_ACTION: "move",
            ATTR_PTZ_ARGUMENT: "up",
        },
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/ptz", "move_up", 0, False
    )


async def test_ptz_preset_service_call(
    hass: HomeAssistant,
    mqtt_mock: Any,
) -> None:
    """Test ptz service call."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PTZ,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_PTZ_ACTION: "preset",
            ATTR_PTZ_ARGUMENT: "main",
        },
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/ptz", "preset_main", 0, False
    )


async def test_ptz_stop_service_call(
    hass: HomeAssistant,
    mqtt_mock: Any,
) -> None:
    """Test ptz service call."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PTZ,
        {
            ATTR_ENTITY_ID: TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            ATTR_PTZ_ACTION: "stop",
        },
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/ptz", "stop", 0, False
    )
