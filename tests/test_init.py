"""Test the frigate binary sensor."""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from . import (
    TEST_CONFIG_ENTRY_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


async def test_entry_unload(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""

    config_entry = await setup_mock_frigate_config_entry(hass)

    config_entries = hass.config_entries.async_entries(DOMAIN)
    assert len(config_entries) == 1
    assert config_entries[0] is config_entry
    assert config_entry.state == ConfigEntryState.LOADED

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.NOT_LOADED


async def test_entry_update(hass: HomeAssistant) -> None:
    """Test updating a config entry."""

    client = create_mock_frigate_client()
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    assert client.async_get_config.call_count == 1

    with patch(
        "custom_components.frigate.FrigateApiClient",
        return_value=client,
    ), patch(
        "custom_components.frigate.media_source.FrigateApiClient", return_value=client
    ):
        assert hass.config_entries.async_update_entry(
            entry=config_entry, title="new title"
        )
        await hass.async_block_till_done()

    # Entry will have been reloaded, and config will be re-fetched.
    assert client.async_get_config.call_count == 2


async def test_entry_async_get_config_fail(hass: HomeAssistant) -> None:
    """Test updating a config entry."""

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(side_effect=FrigateApiClientError)

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    assert config_entry.state == ConfigEntryState.SETUP_RETRY


async def test_entry_migration_v1_to_v2(hass: HomeAssistant) -> None:
    """Test migrating a config entry."""
    entity_registry = er.async_get(hass)

    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data={CONF_HOST: "http://host:456"},
        title="Frigate",
        version=1,
    )

    config_entry.add_to_hass(hass)

    old_unique_ids = [
        ("binary_sensor", "frigate_front_door_person_binary_sensor"),
        ("camera", "frigate_front_door_camera"),
        ("camera", "frigate_front_door_person_snapshot"),
        ("sensor", "frigate_front_door_camera_fps"),
        ("sensor", "frigate_front_door_person"),
        ("sensor", "frigate_detection_fps"),
        ("sensor", "frigate_front_door_process_fps"),
        ("sensor", "frigate_front_door_skipped_fps"),
        ("switch", "frigate_front_door_clips_switch"),
        ("switch", "frigate_front_door_detect_switch"),
        ("switch", "frigate_front_door_snapshots_switch"),
        ("sensor", "frigate_cpu1_inference_speed"),
        ("sensor", "frigate_cpu2_inference_speed"),
        ("sensor", "frigate_front_door_detection_fps"),
        ("sensor", "frigate_steps_person"),
        ("binary_sensor", "frigate_steps_person_binary_sensor"),
    ]

    unrelated_unique_ids = [
        ("cover", "will_match_nothing"),
    ]

    # Create fake entries with the old unique_ids.
    for platform, unique_id in old_unique_ids + unrelated_unique_ids:
        assert entity_registry.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=config_entry
        )

    # Setup the integration.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry
    )

    # Verify the config entry data is as expected.
    assert CONF_HOST not in config_entry.data
    assert CONF_URL in config_entry.data
    assert config_entry.version == 2
    assert config_entry.title == "host:456"

    # Ensure all the old entity unique ids are removed.
    for platform, unique_id in old_unique_ids:
        assert not entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)

    # Ensure all the unrelated entity unique ids are not touched.
    for platform, unique_id in unrelated_unique_ids:
        assert entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)

    # Ensure all the new transformed entity unique ids are present.
    new_unique_ids = [
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:front_door_person"),
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera_snapshots:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_process"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_skipped"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_clips"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_detect"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_snapshots"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_detector_speed:cpu1"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_detector_speed:cpu2"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:steps_person"),
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:steps_person"),
    ]
    for platform, unique_id in new_unique_ids:
        assert (
            entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is not None
        )


async def test_startup_message(caplog: Any, hass: HomeAssistant) -> None:
    """Test the startup message."""

    await setup_mock_frigate_config_entry(hass)

    integration = await async_get_integration(hass, DOMAIN)
    assert integration.version in caplog.text
    assert "This is a custom integration" in caplog.text
