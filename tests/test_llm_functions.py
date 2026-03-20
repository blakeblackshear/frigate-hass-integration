"""Test the Frigate LLM functions."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import ATTR_LLM_UNREGISTER, DOMAIN
from custom_components.frigate.llm_functions import (
    FRIGATE_SERVICES_API_ID,
    FrigateQueryTool,
    FrigateServiceAPI,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from . import create_mock_frigate_client, setup_mock_frigate_config_entry

_LOGGER = logging.getLogger(__name__)


def _create_llm_context() -> llm.LLMContext:
    """Create a test LLMContext with all required fields."""
    return llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant=None,
        device_id=None,
        user_prompt=None,
    )


async def test_frigate_service_api_instance(hass: HomeAssistant) -> None:
    """Test FrigateServiceAPI returns correct API instance."""
    await setup_mock_frigate_config_entry(hass)

    api = FrigateServiceAPI(hass=hass)
    instance = await api.async_get_api_instance(_create_llm_context())

    assert instance.api is api
    assert len(instance.tools) == 1
    assert instance.tools[0].name == "frigate_query"
    assert "front_door" in instance.api_prompt


async def test_frigate_service_api_no_entries(hass: HomeAssistant) -> None:
    """Test FrigateServiceAPI with no config entries."""
    hass.data.setdefault(DOMAIN, {})

    api = FrigateServiceAPI(hass=hass)
    instance = await api.async_get_api_instance(_create_llm_context())

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
    await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone at the front door?"},
    )

    result = await tool.async_call(hass, tool_input, _create_llm_context())

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
    await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={
            "query": "What do you see?",
            "camera_name": "front_door",
        },
    )

    result = await tool.async_call(hass, tool_input, _create_llm_context())

    assert result["response"] == "I can see a car in the driveway."
    client.async_chat_completion.assert_called_once_with(
        "What do you see?", "front_door"
    )


async def test_frigate_query_tool_no_client(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool returns error when no client available."""
    hass.data.setdefault(DOMAIN, {})
    # Add a non-dict entry to exercise the continue guard
    hass.data[DOMAIN]["not_an_entry"] = lambda: None

    tool = FrigateQueryTool(camera_names=[])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone?"},
    )

    result = await tool.async_call(hass, tool_input, _create_llm_context())
    assert "error" in result


async def test_frigate_query_tool_api_error(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool handles API errors gracefully."""
    client = create_mock_frigate_client()
    client.async_chat_completion = AsyncMock(
        side_effect=FrigateApiClientError("Connection failed")
    )
    await setup_mock_frigate_config_entry(hass, client=client)

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Is there anyone?"},
    )

    result = await tool.async_call(hass, tool_input, _create_llm_context())
    assert "error" in result


async def test_frigate_query_tool_skips_non_entry_data(hass: HomeAssistant) -> None:
    """Test FrigateQueryTool skips non-dict entries like llm_unregister callback."""
    client = create_mock_frigate_client()
    client.async_chat_completion = AsyncMock(
        return_value={
            "message": {"role": "assistant", "content": "All clear."},
            "finish_reason": "stop",
            "tool_iterations": 0,
            "tool_calls": [],
        }
    )
    await setup_mock_frigate_config_entry(hass, client=client)

    # ATTR_LLM_UNREGISTER is now in hass.data[DOMAIN] as a callable (non-dict)
    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]

    tool = FrigateQueryTool(camera_names=["front_door"])
    tool_input = llm.ToolInput(
        tool_name="frigate_query",
        tool_args={"query": "Anything happening?"},
    )
    result = await tool.async_call(hass, tool_input, _create_llm_context())
    assert result["response"] == "All clear."


async def test_frigate_service_api_skips_non_entry_data(hass: HomeAssistant) -> None:
    """Test FrigateServiceAPI skips non-dict entries when collecting cameras."""
    await setup_mock_frigate_config_entry(hass)

    # ATTR_LLM_UNREGISTER is now in hass.data[DOMAIN] as a callable (non-dict)
    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]

    api = FrigateServiceAPI(hass=hass)
    instance = await api.async_get_api_instance(_create_llm_context())
    assert "front_door" in instance.api_prompt


async def test_llm_api_registration_with_version_018(hass: HomeAssistant) -> None:
    """Test LLM API is registered when Frigate version is 0.18+."""
    await setup_mock_frigate_config_entry(hass)

    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]
    apis = llm.async_get_apis(hass)
    api_ids = [api.id for api in apis]
    assert FRIGATE_SERVICES_API_ID in api_ids


async def test_llm_api_unregistered_on_last_entry_unload(
    hass: HomeAssistant,
) -> None:
    """Test LLM API is unregistered when last config entry is unloaded."""
    config_entry = await setup_mock_frigate_config_entry(hass)
    assert ATTR_LLM_UNREGISTER in hass.data[DOMAIN]

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert ATTR_LLM_UNREGISTER not in hass.data[DOMAIN]
    apis = llm.async_get_apis(hass)
    api_ids = [api.id for api in apis]
    assert FRIGATE_SERVICES_API_ID not in api_ids
