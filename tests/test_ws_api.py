"""Test the Frigate HA websocket API."""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

from custom_components.frigate.api import FrigateApiClientError
from homeassistant.core import HomeAssistant

from tests import (
    TEST_FRIGATE_INSTANCE_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

TEST_CAMERA = "front_door"
TEST_EVENT_ID = "1656282822.206673-bovnfg"
TEST_LABEL = "person"
TEST_SUB_LABEL = "mr-frigate"
TEST_ZONE = "steps"


async def test_retain_success(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test un/retaining an event."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    retain_json: dict[str, Any] = {
        "id": 1,
        "type": "frigate/event/retain",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "event_id": TEST_EVENT_ID,
        "retain": True,
    }

    retain_success = {"retain": "success"}
    mock_client.async_retain = AsyncMock(return_value=retain_success)
    await ws_client.send_json(retain_json)

    response = await ws_client.receive_json()
    mock_client.async_retain.assert_called_with(TEST_EVENT_ID, True, decode_json=False)
    assert response["success"]
    assert response["result"] == retain_success

    unretain_success = {"unretain": "success"}
    mock_client.async_retain = AsyncMock(return_value=unretain_success)
    await ws_client.send_json(
        {
            **retain_json,
            "id": 2,
            "retain": False,
        }
    )

    response = await ws_client.receive_json()
    mock_client.async_retain.assert_called_with(TEST_EVENT_ID, False, decode_json=False)
    assert response["success"]
    assert response["result"] == unretain_success


async def test_retain_missing_args(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retaining an event with missing arguments."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    retain_json = {
        "id": 1,
        "type": "frigate/event/retain",
    }

    await ws_client.send_json(retain_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_format"


async def test_retain_instance_not_found(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retaining an event with an instance that is not found."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    retain_json = {
        "id": 1,
        "type": "frigate/event/retain",
        "instance_id": "THIS-IS-NOT-A-REAL-INSTANCE-ID",
        "event_id": TEST_EVENT_ID,
        "retain": True,
    }

    await ws_client.send_json(retain_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_retain_api_error(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retaining an event when the API has an error."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    retain_json = {
        "id": 1,
        "type": "frigate/event/retain",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "event_id": TEST_EVENT_ID,
        "retain": True,
    }

    mock_client.async_retain = AsyncMock(side_effect=FrigateApiClientError)

    await ws_client.send_json(retain_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"


async def test_get_recordings_success(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retrieving recordings successfully."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    recording_json: dict[str, Any] = {
        "id": 1,
        "type": "frigate/recordings/summary",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "camera": TEST_CAMERA,
    }

    recording_success = {"recording": "summary"}
    mock_client.async_get_recordings_summary = AsyncMock(return_value=recording_success)
    await ws_client.send_json({**recording_json, "timezone": "Europe/Dublin"})

    response = await ws_client.receive_json()
    mock_client.async_get_recordings_summary.assert_called_with(
        TEST_CAMERA, "Europe/Dublin", decode_json=False
    )
    assert response["success"]
    assert response["result"] == recording_success

    recording_success = {"recording": "get"}
    after = 1
    before = 2
    mock_client.async_get_recordings = AsyncMock(return_value=recording_success)
    await ws_client.send_json(
        {
            **recording_json,
            "id": 2,
            "type": "frigate/recordings/get",
            "after": after,
            "before": before,
        }
    )

    response = await ws_client.receive_json()
    mock_client.async_get_recordings.assert_called_with(
        TEST_CAMERA, after, before, decode_json=False
    )
    assert response["success"]
    assert response["result"] == recording_success


async def test_get_recordings_instance_not_found(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving recordings from a non-existent instance."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    recording_json = {
        "id": 1,
        "type": "frigate/recordings/summary",
        "instance_id": "THIS-IS-NOT-A-REAL-INSTANCE-ID",
        "camera": TEST_CAMERA,
    }

    await ws_client.send_json(recording_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"

    await ws_client.send_json(
        {
            **recording_json,
            "id": 2,
            "type": "frigate/recordings/get",
        }
    )
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_get_recordings_api_error(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving recordings when the API has an error."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    recording_json = {
        "id": 1,
        "type": "frigate/recordings/summary",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "camera": TEST_CAMERA,
    }

    mock_client.async_get_recordings_summary = AsyncMock(
        side_effect=FrigateApiClientError
    )

    await ws_client.send_json(recording_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"

    mock_client.async_get_recordings = AsyncMock(side_effect=FrigateApiClientError)

    await ws_client.send_json(
        {
            **recording_json,
            "id": 2,
            "type": "frigate/recordings/get",
        }
    )
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"


async def test_get_events_success(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retrieving events successfully."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    events_json = {
        "id": 1,
        "type": "frigate/events/get",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "cameras": [TEST_CAMERA],
        "labels": [TEST_LABEL],
        "sub_labels": [TEST_SUB_LABEL],
        "zones": [TEST_ZONE],
        "after": 1,
        "before": 2,
        "limit": 3,
        "has_clip": True,
        "has_snapshot": True,
        "favorites": True,
    }

    events_success = {"events": "summary"}
    mock_client.async_get_events = AsyncMock(return_value=events_success)
    await ws_client.send_json(events_json)

    response = await ws_client.receive_json()
    mock_client.async_get_events.assert_called_with(
        [TEST_CAMERA],
        [TEST_LABEL],
        [TEST_SUB_LABEL],
        [TEST_ZONE],
        1,
        2,
        3,
        True,
        True,
        True,
        decode_json=False,
    )
    assert response["success"]
    assert response["result"] == events_success


async def test_get_events_instance_not_found(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving events from a non-existent instance."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    events_json = {
        "id": 1,
        "type": "frigate/events/get",
        "instance_id": "THIS-IS-NOT-A-REAL-INSTANCE-ID",
        "cameras": [TEST_CAMERA],
    }

    await ws_client.send_json(events_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_get_events_api_error(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retrieving events when the API has an error."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    recording_json = {
        "id": 1,
        "type": "frigate/events/get",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "cameras": [TEST_CAMERA],
    }

    mock_client.async_get_events = AsyncMock(side_effect=FrigateApiClientError)

    await ws_client.send_json(recording_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"


async def test_get_events_summary_success(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving events summary successfully."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    events_summary_json = {
        "id": 1,
        "type": "frigate/events/summary",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "has_clip": True,
        "has_snapshot": True,
        "timezone": "US/Pacific",
    }

    events_summary_success = {"events": "summary"}
    mock_client.async_get_event_summary = AsyncMock(return_value=events_summary_success)
    await ws_client.send_json(events_summary_json)

    response = await ws_client.receive_json()
    mock_client.async_get_event_summary.assert_called_with(
        True, True, "US/Pacific", decode_json=False
    )
    assert response["success"]
    assert response["result"] == events_summary_success


async def test_get_events_summary_instance_not_found(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving events summary from a non-existent instance."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    events_summary_json = {
        "id": 1,
        "type": "frigate/events/summary",
        "instance_id": "THIS-IS-NOT-A-REAL-INSTANCE-ID",
    }

    await ws_client.send_json(events_summary_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_get_events_summary_api_error(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving events summary when the API has an error."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    events_summary_json = {
        "id": 1,
        "type": "frigate/events/summary",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
    }

    mock_client.async_get_event_summary = AsyncMock(side_effect=FrigateApiClientError)

    await ws_client.send_json(events_summary_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"


async def test_get_ptz_info_success(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retrieving PTZ info successfully."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    ptz_info_json = {
        "id": 1,
        "type": "frigate/ptz/info",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "camera": "master_bedroom",
    }
    ptz_info_success = {
        "features": ["pt", "zoom", "pt-r", "zoom-r"],
        "name": "master_bedroom",
        "presets": [
            "preset01",
            "preset02",
        ],
    }
    mock_client.async_get_ptz_info = AsyncMock(return_value=ptz_info_success)
    await ws_client.send_json(ptz_info_json)

    response = await ws_client.receive_json()
    mock_client.async_get_ptz_info.assert_called_with(
        "master_bedroom", decode_json=False
    )
    assert response["success"]
    assert response["result"] == ptz_info_success


async def test_get_ptz_info_instance_not_found(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Test retrieving PTZ info from a non-existent instance."""

    await setup_mock_frigate_config_entry(hass)

    ws_client = await hass_ws_client()
    ptz_info_json = {
        "id": 1,
        "type": "frigate/ptz/info",
        "instance_id": "THIS-IS-NOT-A-REAL-INSTANCE-ID",
        "camera": "master_bedroom",
    }

    await ws_client.send_json(ptz_info_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_get_ptz_info_api_error(hass: HomeAssistant, hass_ws_client: Any) -> None:
    """Test retrieving PTZ info when the API has an error."""

    mock_client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=mock_client)

    ws_client = await hass_ws_client()
    ptz_info_json = {
        "id": 1,
        "type": "frigate/ptz/info",
        "instance_id": TEST_FRIGATE_INSTANCE_ID,
        "camera": "master_bedroom",
    }

    mock_client.async_get_ptz_info = AsyncMock(side_effect=FrigateApiClientError)

    await ws_client.send_json(ptz_info_json)
    response = await ws_client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "frigate_error"
