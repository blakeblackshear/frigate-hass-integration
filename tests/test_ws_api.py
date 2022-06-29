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

TEST_EVENT_ID = "1656282822.206673-bovnfg"


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
    mock_client.async_retain.assert_called_with(TEST_EVENT_ID, True)
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
    mock_client.async_retain.assert_called_with(TEST_EVENT_ID, False)
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
