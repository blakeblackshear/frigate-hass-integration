"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import DOMAIN, NAME, VERSION
from homeassistant.components.camera import async_get_image, async_get_stream_source
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    TEST_CAMERA_FRONT_DOOR_ENTITY_ID,
    TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID,
    TEST_CONFIG,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__package__)


async def test_frigate_camera_setup(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up a camera."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "idle"
    assert entity_state.attributes["supported_features"] == 2

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtmp://example.com/live/front_door"

    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg?h=277",
        content=b"data",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert image
    assert image.content == b"data"


async def test_frigate_camera_setup_no_stream(hass: HomeAssistant) -> None:
    """Set up a camera without streaming."""

    config = copy.deepcopy(TEST_CONFIG)
    config["cameras"]["front_door"]["rtmp"]["enabled"] = False
    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)
    await setup_mock_frigate_config_entry(hass, client=client)

    entity_state = hass.states.get(TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "idle"
    assert not entity_state.attributes["supported_features"]

    assert not await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)


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
    assert device.model == VERSION

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_CAMERA_FRONT_DOOR_ENTITY_ID in entities_from_device
    assert TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID in entities_from_device
