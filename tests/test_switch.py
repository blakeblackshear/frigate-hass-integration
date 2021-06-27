"""Test the frigate switch."""
from __future__ import annotations

import logging
from typing import Any

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.frigate.const import DOMAIN, NAME
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    TEST_CONFIG_ENTRY_ID,
    TEST_SERVER_VERSION,
    TEST_SWITCH_FRONT_DOOR_CLIPS_ENTITY_ID,
    TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID,
    TEST_SWITCH_FRONT_DOOR_SNAPSHOTS_ENTITY_ID,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)

SWITCH_ENTITY_IDS = [
    TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID,
    TEST_SWITCH_FRONT_DOOR_CLIPS_ENTITY_ID,
    TEST_SWITCH_FRONT_DOOR_SNAPSHOTS_ENTITY_ID,
]


async def test_switch_state(hass: HomeAssistant) -> None:
    """Verify a successful binary sensor setup."""
    await setup_mock_frigate_config_entry(hass)

    for entity_id in SWITCH_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state == "unavailable"

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    for entity_id in SWITCH_ENTITY_IDS:
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/detect/state", "ON")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "on"

    async_fire_mqtt_message(hass, "frigate/front_door/detect/state", "OFF")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/front_door/detect/state", "INVALID_VALUE")
    await hass.async_block_till_done()
    entity_state = hass.states.get(TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "off"

    async_fire_mqtt_message(hass, "frigate/available", "offline")
    entity_state = hass.states.get(TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID)
    assert entity_state
    assert entity_state.state == "unavailable"


async def test_switch_turn_on(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify turning a switch on."""
    await setup_mock_frigate_config_entry(hass)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/detect/set", "ON", 0, True
    )


async def test_switch_turn_off(hass: HomeAssistant, mqtt_mock: Any) -> None:
    """Verify turning a switch off."""
    await setup_mock_frigate_config_entry(hass)

    async_fire_mqtt_message(hass, "frigate/available", "online")
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        "frigate/front_door/detect/set", "OFF", 0, True
    )


async def test_switch_device_info(hass: HomeAssistant) -> None:
    """Verify switch device information."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{config_entry.entry_id}:front_door")}
    )
    assert device
    assert device.manufacturer == NAME
    assert device.model.endswith(f"/{TEST_SERVER_VERSION}")

    entity_registry = await er.async_get_registry(hass)
    entities_from_device = [
        entry.entity_id
        for entry in er.async_entries_for_device(entity_registry, device.id)
    ]
    for entity_id in SWITCH_ENTITY_IDS:
        assert entity_id in entities_from_device


async def test_switch_icon(hass: HomeAssistant) -> None:
    """Verify switch device information."""
    await setup_mock_frigate_config_entry(hass)

    expected_results = {
        TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID: "hass:motion-sensor",
        TEST_SWITCH_FRONT_DOOR_CLIPS_ENTITY_ID: "mdi:filmstrip-box-multiple",
        TEST_SWITCH_FRONT_DOOR_SNAPSHOTS_ENTITY_ID: "mdi:image-multiple",
    }

    for entity_id, icon in expected_results.items():
        entity_state = hass.states.get(entity_id)
        assert entity_state
        assert entity_state.attributes["icon"] == icon


async def test_switch_unique_id(hass: HomeAssistant) -> None:
    """Verify entity unique_id(s)."""
    await setup_mock_frigate_config_entry(hass)
    registry_entry = er.async_get(hass).async_get(
        TEST_SWITCH_FRONT_DOOR_DETECT_ENTITY_ID
    )
    assert registry_entry
    assert (
        registry_entry.unique_id == f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_detect"
    )
