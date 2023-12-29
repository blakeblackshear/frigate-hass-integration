"""Test the frigate image."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import (
    TEST_CONFIG_ENTRY_ID,
    TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID,
    setup_mock_frigate_config_entry,
    verify_entities_are_setup_correctly_in_registry,
)

_LOGGER = logging.getLogger(__name__)


async def test_frigate_mqtt_snapshots_image_setup(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    """Set up an mqtt image."""

    await setup_mock_frigate_config_entry(hass)

    entity_state = hass.states.get(TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state

    async_fire_mqtt_message(hass, "frigate/front_door/person/snapshot", "mqtt_data")
    await hass.async_block_till_done()

    entity_state = hass.states.get(TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID)
    assert entity_state
    assert datetime.datetime.strptime(entity_state.state, "%Y-%m-%dT%H:%M:%S.%f")


@pytest.mark.parametrize(
    "entityid_to_uniqueid",
    [
        (
            TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID,
            f"{TEST_CONFIG_ENTRY_ID}:image_best_snapshot:front_door_person",
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


async def test_cameras_setup_correctly_in_registry(
    aiohttp_server: Any, hass: HomeAssistant
) -> None:
    """Verify entities are enabled/visible as appropriate."""

    await setup_mock_frigate_config_entry(hass)
    await verify_entities_are_setup_correctly_in_registry(
        hass,
        entities_enabled={
            TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID,
        },
        entities_visible={
            TEST_IMAGE_FRONT_DOOR_PERSON_ENTITY_ID,
        },
    )
