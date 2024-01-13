"""Test the frigate binary sensor."""
from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate import (
    get_frigate_device_identifier,
    get_frigate_entity_unique_id,
)
from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import CONF_CAMERA_STATIC_IMAGE_HEIGHT, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.loader import async_get_integration

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
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


async def test_entry_async_get_version_incompatible(hass: HomeAssistant) -> None:
    """Test running an incompatible server version."""

    client = create_mock_frigate_client()
    client.async_get_version = AsyncMock(return_value="0.8.4-1234567")

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    print(config_entry.state)
    assert config_entry.state == ConfigEntryState.SETUP_ERROR


async def test_entry_async_get_version_compatible_leading_zero(
    hass: HomeAssistant,
) -> None:
    """Test running an incompatible server version."""

    client = create_mock_frigate_client()
    client.async_get_version = AsyncMock(return_value="0.13.0-0858859")

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    print(config_entry.state)
    assert config_entry.state == ConfigEntryState.LOADED


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
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:front_door_person"),
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_process"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_skipped"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_recordings"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_detect"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_snapshots"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_detector_speed:cpu1"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_detector_speed:cpu2"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:steps_person"),
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:steps_person"),
    ]
    for platform, unique_id in new_unique_ids:
        assert (
            entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is not None
        )


async def test_entry_cleanup_old_clips_switch(hass: HomeAssistant) -> None:
    """Test cleanup of old clips switch."""
    entity_registry = er.async_get(hass)

    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data={CONF_HOST: "http://host:456"},
        title="Frigate",
        version=2,
    )

    config_entry.add_to_hass(hass)

    old_unique_ids = [
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:front_door_person"),
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
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
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:steps_person"),
    ]

    # Create fake entries with the old unique_ids.
    for platform, unique_id in old_unique_ids:
        assert entity_registry.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=config_entry
        )

    # Setup the integration.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry
    )

    for platform, unique_id in old_unique_ids:
        if platform == "switch" and unique_id.endswith("_clips"):
            assert (
                entity_registry.async_get_entity_id("switch", DOMAIN, unique_id) is None
            )
        else:
            assert (
                entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
                is not None
            )

    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_recordings"
        )
        is not None
    )


async def test_entry_cleanup_old_motion_sensor(hass: HomeAssistant) -> None:
    """Test cleanup of old motion sensor."""
    entity_registry = er.async_get(hass)

    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data={CONF_HOST: "http://host:456"},
        title="Frigate",
        version=2,
    )

    config_entry.add_to_hass(hass)

    old_unique_ids = {
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:front_door_person"),
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:steps_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_process"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_skipped"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_recordings"),
    }

    # Create fake entries with the old unique_ids.
    for platform, unique_id in old_unique_ids:
        assert entity_registry.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=config_entry
        )

    # Setup the integration.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry
    )

    removed_unique_ids = {
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:front_door_person"),
        ("binary_sensor", f"{TEST_CONFIG_ENTRY_ID}:motion_sensor:steps_person"),
    }

    for platform, unique_id in removed_unique_ids:
        assert entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is None

    for platform, unique_id in old_unique_ids - removed_unique_ids:
        assert (
            entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is not None
        )


async def test_entry_rename_object_count_sensor(hass: HomeAssistant) -> None:
    """Test cleanup of old motion sensor."""
    entity_registry = er.async_get(hass)

    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data={CONF_HOST: "http://host:456"},
        title="Frigate",
        version=2,
    )

    config_entry.add_to_hass(hass)

    old_unique_ids = {
        (
            "binary_sensor",
            f"{TEST_CONFIG_ENTRY_ID}:occupancy_sensor:front_door_person",
            "binary_sensor.front_door_person_occupancy",
        ),
        (
            "sensor",
            f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera",
            "sensor.front_door_camera_fps",
        ),
        (
            "sensor",
            f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person",
            "sensor.front_door_person_count",
        ),
    }

    # Create fake entries with the old unique_ids.
    for platform, unique_id, _ in old_unique_ids:
        assert entity_registry.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=config_entry
        )

    # Setup the integration.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry
    )

    renamed_unique_ids = {
        (
            "sensor",
            f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person",
            "sensor.front_door_person_count",
        ),
    }

    for platform, unique_id, entity_id in renamed_unique_ids:
        found_entity_id = entity_registry.async_get_entity_id(
            platform, DOMAIN, unique_id
        )
        assert found_entity_id is not None
        assert found_entity_id == entity_id

    for platform, unique_id, _ in old_unique_ids - renamed_unique_ids:
        assert (
            entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is not None
        )


async def test_entry_cleanup_old_camera_snapshot(hass: HomeAssistant) -> None:
    """Test cleanup of old camera snapshot."""
    entity_registry = er.async_get(hass)

    config_entry: MockConfigEntry = MockConfigEntry(
        entry_id=TEST_CONFIG_ENTRY_ID,
        domain=DOMAIN,
        data={CONF_HOST: "http://host:456"},
        title="Frigate",
        version=2,
    )

    config_entry.add_to_hass(hass)

    old_unique_ids = {
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera:front_door"),
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera_snapshots:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_camera"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_object_count:front_door_person"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:detection"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_process"),
        ("sensor", f"{TEST_CONFIG_ENTRY_ID}:sensor_fps:front_door_skipped"),
        ("switch", f"{TEST_CONFIG_ENTRY_ID}:switch:front_door_recordings"),
    }

    # Create fake entries with the old unique_ids.
    for platform, unique_id in old_unique_ids:
        assert entity_registry.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=config_entry
        )

    # Setup the integration.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry
    )

    removed_unique_ids = {
        ("camera", f"{TEST_CONFIG_ENTRY_ID}:camera_snapshots:front_door_person"),
    }

    for platform, unique_id in removed_unique_ids:
        assert entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is None

    for platform, unique_id in old_unique_ids - removed_unique_ids:
        assert (
            entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) is not None
        )


async def test_startup_message(caplog: Any, hass: HomeAssistant) -> None:
    """Test the startup message."""

    await setup_mock_frigate_config_entry(hass)

    integration = await async_get_integration(hass, DOMAIN)
    assert integration.version in caplog.text
    assert "This is a custom integration" in caplog.text


async def test_entry_remove_old_image_height_option(hass: HomeAssistant) -> None:
    """Test cleanup of old image height option."""

    config_entry = create_mock_frigate_config_entry(
        hass, options={CONF_CAMERA_STATIC_IMAGE_HEIGHT: 42}
    )

    await setup_mock_frigate_config_entry(hass, config_entry)

    assert (
        CONF_CAMERA_STATIC_IMAGE_HEIGHT
        not in hass.config_entries.async_get_entry(config_entry.entry_id).options
    )


async def test_entry_remove_old_devices(hass: HomeAssistant) -> None:
    """Test that old devices (not on the Frigate server) are removed."""

    config_entry = create_mock_frigate_config_entry(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    # Create some random old devices/entity_ids and ensure they get cleaned up.
    bad_device_id = "bad-device-id"
    bad_entity_unique_id = "bad-entity-unique_id"
    bad_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, bad_device_id)}
    )
    entity_registry.async_get_or_create(
        domain=DOMAIN,
        platform="camera",
        unique_id=bad_entity_unique_id,
        config_entry=config_entry,
        device_id=bad_device.id,
    )

    config_entry = await setup_mock_frigate_config_entry(hass)
    await hass.async_block_till_done()

    # Device: Ensure the master device is still present.
    assert device_registry.async_get_device(
        {get_frigate_device_identifier(config_entry)}
    )

    # # Device: Ensure the old device is removed.
    assert not device_registry.async_get_device({(DOMAIN, bad_device_id)})

    # Device: Ensure a valid camera device is still present.
    assert device_registry.async_get_device(
        {get_frigate_device_identifier(config_entry, "front_door")}
    )

    # Device: Ensure a valid zone is still present.
    assert device_registry.async_get_device(
        {get_frigate_device_identifier(config_entry, "steps")}
    )

    # Entity: Ensure the old registered entity is removed.
    assert not entity_registry.async_get_entity_id(
        DOMAIN, "camera", bad_entity_unique_id
    )

    # Entity: Ensure an entity for a valid camera remains.
    assert entity_registry.async_get_entity_id(
        "camera",
        DOMAIN,
        get_frigate_entity_unique_id(config_entry.entry_id, "camera", "front_door"),
    )

    # Entity: Ensure an entity for a valid zone remains.
    assert entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        get_frigate_entity_unique_id(
            config_entry.entry_id, "sensor_object_count", "steps_person"
        ),
    )


async def test_entry_rename_entities_with_unusual_names(hass: HomeAssistant) -> None:
    """Test that non-simple names work."""
    # Test for: https://github.com/blakeblackshear/frigate-hass-integration/issues/275

    config: dict[str, Any] = copy.deepcopy(TEST_CONFIG)

    # Rename one camera.
    config["cameras"]["Front-door"] = config["cameras"]["front_door"]
    del config["cameras"]["front_door"]

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config)

    config_entry = create_mock_frigate_config_entry(hass)
    unique_id = get_frigate_entity_unique_id(
        config_entry.entry_id,
        "sensor_object_count",
        "Front-door_person",
    )

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id=unique_id,
        config_entry=config_entry,
        suggested_object_id="front_door_person",
    )

    # Verify the entity name before we load the config entry.
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id == "sensor.front_door_person"

    # Load the config entry.
    config_entry = await setup_mock_frigate_config_entry(
        hass, config_entry=config_entry, client=client
    )
    await hass.async_block_till_done()

    # Verify the rename has correctly occurred.
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id == "sensor.front_door_person_count"
