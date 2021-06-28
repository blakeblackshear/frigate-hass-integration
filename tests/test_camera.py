"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import (
    CONF_CAMERA_STATIC_IMAGE_HEIGHT,
    CONF_RTMP_URL_TEMPLATE,
    DOMAIN,
    NAME,
)
from homeassistant.components.camera import async_get_image, async_get_stream_source
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
)

_LOGGER = logging.getLogger(__name__)


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
        content=b"data-277",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert image
    assert image.content == b"data-277"


async def test_frigate_camera_image_height_option(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up a camera with a custom static image height."""

    client = create_mock_frigate_client()

    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_CAMERA_STATIC_IMAGE_HEIGHT: 1000}
    )
    await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )

    aioclient_mock.get(
        "http://example.com/api/front_door/latest.jpg?h=1000",
        content=b"data-1000",
    )

    image = await async_get_image(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert image
    assert image.content == b"data-1000"

    # Set the image height to 0 (in which case no argument is passed)
    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ):
        hass.config_entries.async_update_entry(
            config_entry, options={CONF_CAMERA_STATIC_IMAGE_HEIGHT: 0}
        )
        await hass.async_block_till_done()

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
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    assert TEST_CAMERA_FRONT_DOOR_ENTITY_ID in entities_from_device
    assert TEST_CAMERA_FRONT_DOOR_PERSON_ENTITY_ID in entities_from_device


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


async def test_camera_option_stream_url_template(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify camera with the RTMP URL template option."""

    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_RTMP_URL_TEMPLATE: ("rtmp://localhost/{{ name }}")}
    )
    await setup_mock_frigate_config_entry(hass, config_entry=config_entry)

    source = await async_get_stream_source(hass, TEST_CAMERA_FRONT_DOOR_ENTITY_ID)
    assert source
    assert source == "rtmp://localhost/front_door"
