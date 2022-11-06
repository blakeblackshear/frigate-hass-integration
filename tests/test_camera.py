"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import (
    ATTR_EVENT_ID,
    ATTR_FAVORITE,
    CONF_RTMP_URL_TEMPLATE,
    CONF_RTSP_URL_TEMPLATE,
    DOMAIN,
    NAME,
    SERVICE_FAVORITE_EVENT,
)
from homeassistant.components.camera import (
    DOMAIN as CAMERA_DOMAIN,
    SERVICE_DISABLE_MOTION,
    SERVICE_ENABLE_MOTION,
    async_get_image,
    async_get_stream_source,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
    TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    TEST_SERVER_VERSION,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
    setup_mock_frigate_config_entry,
    test_entities_are_setup_correctly_in_registry,
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


async def test_frigate_camera_setup_rtmp(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up a camera."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["restream"]["enabled"] = False
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


async def test_frigate_camera_setup_no_stream(hass: HomeAssistant) -> None:
    """Set up a camera without streaming."""

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["restream"]["enabled"] = False
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
    config["cameras"]["front_door"]["restream"]["enabled"] = False
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


async def test_frigate_mqtt_snapshots_camera_setup(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up an mqtt camera."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"
    assert entity_state.attributes["supported_features"] == 0

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "idle"

    async_fire_mqtt_message(hass, "frigate/front_door/person/snapshot", "mqtt_data")
    await hass.async_block_till_done()

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID)
    assert image
    assert image.content == b"mqtt_data"

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "active"


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
    assert TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID in entities_from_device


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


@pytest.mark.parametrize(
    "entityid_to_uniqueid",
    [
        (TEST_CAMERA_FRONT_DOOR_ENTITY_ID, f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
        (
            TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:camera_snapshots:front_door_person",
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


async def test_camera_option_rtsp_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify camera with the RTSP URL template option."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["restream"]["enabled"] = True
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


async def test_camera_option_rtmp_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify camera with the RTMP URL template option."""
    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["restream"]["enabled"] = False
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
    await test_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={
            TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID,
        },
        entities_visible={
            TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
            TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID,
        },
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
