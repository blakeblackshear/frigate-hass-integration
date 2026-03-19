"""Test the Frigate LLM functions."""

from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import (
    ATTR_CLIENT,
    ATTR_CONFIG,
    ATTR_LLM_UNREGISTER,
    DOMAIN,
)
from custom_components.frigate.llm_functions import (
    FRIGATE_SERVICES_API_ID,
    FrigateQueryTool,
    FrigateServiceAPI,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from . import (
    TEST_CONFIG,
    TEST_CONFIG_ENTRY_ID,
    create_mock_frigate_client,
    setup_mock_frigate_config_entry,
)

_LOGGER = logging.getLogger(__name__)


async def test_frigate_service_api_instance(hass: HomeAssistant) -> None:
    """Test FrigateServiceAPI returns correct API instance."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    api = FrigateServiceAPI(hass=hass)
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )
    instance = await api.async_get_api_instance(llm_context)

    assert instance.api is api
    assert len(instance.tools) == 1
    assert instance.tools[0].name == "frigate_query"
    assert "front_door" in instance.api_prompt


async def test_frigate_service_api_no_entries(hass: HomeAssistant) -> None:
    """Test FrigateServiceAPI with no config entries."""
    hass.data.setdefault(DOMAIN, {})

    api = FrigateServiceAPI(hass=hass)
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )
    instance = await api.async_get_api_instance(llm_context)

    assert len(instance.tools) == 1
    assert "none detected" in instance.api_prompt


async def test_frigate_query_tool_call(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool calls the chat completion API."""
    client = create_mock_frigate_client()
    client.async_chat_completion = AsyncMock(
        return_value={
            "message": {
                "role": "assistant",
                "content": "There is a person at the front door.",
            },
            "finish_reason": "stop",
            "tool_iterations": 1,
            "tool_calls": [],
        }
    )
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone at the front door?"},
    )
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )

    result = await tool.async_call(hass, tool_input, llm_context)

    assert result["response"] == "There is a person at the front door."
    client.async_chat_completion.assert_called_once_with(
        "Is there anyone at the front door?", None
    )


async def test_frigate_query_tool_with_camera(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool passes camera name for live image."""
    client = create_mock_frigate_client()
    client.async_chat_completion = AsyncMock(
        return_value={
            "message": {
                "role": "assistant",
                "content": "I can see a car in the driveway.",
            },
            "finish_reason": "stop",
            "tool_iterations": 1,
            "tool_calls": [],
        }
    )
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={
            "query": "What do you see?",
            "camera_name": "front_door",
        },
    )
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )

    result = await tool.async_call(hass, tool_input, llm_context)

    assert result["response"] == "I can see a car in the driveway."
    client.async_chat_completion.assert_called_once_with(
        "What do you see?", "front_door"
    )


async def test_frigate_query_tool_no_client(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool returns error when no client available."""
    hass.data.setdefault(DOMAIN, {})

    tool = FrigateQueryTool(camera_names=[])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone?"},
    )
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )

    result = await tool.async_call(hass, tool_input, llm_context)
    assert "error" in result


async def test_frigate_query_tool_api_error(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool handles API errors gracefully."""
    client = create_mock_frigate_client()
    client.async_chat_completion = AsyncMock(
        side_effect=FrigateApiClientError("Connection failed")
    )
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone?"},
    )
    llm_context = llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
    )

    result = await tool.async_call(hass, tool_input, llm_context)
    assert "error" in result


async def test_llm_api_registration_with_version_018(hass: HomeAssistant) -> None:
    """Test LLM API is registered when Frigate version is 0.18+."""
    client = create_mock_frigate_client()
    config = copy.deepcopy(TEST_CONFIG)
    config["version"] = "0.18.0"
    client.async_get_config = AsyncMock(return_value=config)

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)

    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]
    # Verify the API is registered
    apis = llm.async_get_apis(hass)
    api_ids = [api.id for api in apis]
    assert FRIGATE_SERVICES_API_ID in api_ids


async def test_llm_api_not_registered_with_version_017(hass: HomeAssistant) -> None:
    """Test LLM API is not registered when Frigate version is below 0.18."""
    config_entry = await setup_mock_frigate_config_entry(hass)

    assert ATTR_LLM_UNREGISTER not in hass.data[DOMAIN]


async def test_llm_api_unregistered_on_last_entry_unload(
    hass: HomeAssistant,
) -> None:
    """Test LLM API is unregistered when last config entry is unloaded."""
    client = create_mock_frigate_client()
    config = copy.deepcopy(TEST_CONFIG)
    config["version"] = "0.18.0"
    client.async_get_config = AsyncMock(return_value=config)

    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert ATTR_LLM_UNREGISTER not in hass.data[DOMAIN]
    apis = llm.async_get_apis(hass)
    api_ids = [api.id for api in apis]
    assert FRIGATE_SERVICES_API_ID not in api_ids
