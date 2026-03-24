"""LLM API for Frigate integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.util.json import JsonObjectType

from .api import FrigateApiClientError
from .const import ATTR_CLIENT, ATTR_CONFIG, DOMAIN

_LOGGER = logging.getLogger(__name__)

FRIGATE_SERVICES_API_ID = "frigate_services"


class FrigateQueryTool(llm.Tool):
    """Tool that queries the Frigate NVR chat API."""

    name = "frigate_query"
    description = (
        "Query Frigate NVR. Use when the user asks about anything cameras could "
        "answer — people, vehicles, packages, animals, "
        "or what is happening in a physical area outside the home. "
        "Also use when the user wants to be notified or alerted when something "
        "visually observable occurs at a monitored location. "
        "Forward the user's request as-is; Frigate handles tool selection internally."
    )

    def __init__(self, camera_names: list[str]) -> None:
        """Initialize the tool with available camera names."""
        schema: dict[vol.Marker, Any] = {
            vol.Required(
                "query",
                description="The user's question or request, forwarded as-is.",
            ): cv.string,
        }
        if camera_names:
            schema[
                vol.Optional(
                    "camera_name",
                    description="Camera name to include a live image for visual context.",
                )
            ] = vol.In(camera_names)
        self.parameters = vol.Schema(schema)

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the Frigate chat completion API."""
        query = tool_input.tool_args["query"]
        camera_name = tool_input.tool_args.get("camera_name")

        # Find the right client
        client = None
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if not isinstance(entry_data, dict) or ATTR_CLIENT not in entry_data:
                continue
            if camera_name:
                config = entry_data.get(ATTR_CONFIG, {})
                if camera_name in config.get("cameras", {}):
                    client = entry_data[ATTR_CLIENT]
                    break
            else:
                client = entry_data[ATTR_CLIENT]
                break

        if client is None:
            return {"error": "No Frigate instance available"}

        try:
            result = await client.async_chat_completion(query, camera_name)
            content = result.get("message", {}).get("content", "")
            return {"response": content}
        except FrigateApiClientError as exc:
            _LOGGER.error("Frigate query failed: %s", exc)
            return {"error": f"Frigate query failed: {exc}"}


class FrigateServiceAPI(llm.API):
    """LLM API exposing Frigate Services."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the API."""
        super().__init__(
            hass=hass,
            id=FRIGATE_SERVICES_API_ID,
            name="Frigate Services",
        )

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the instance of the API."""
        # Collect camera names from all Frigate config entries
        camera_names: list[str] = []
        for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
            if not isinstance(entry_data, dict) or ATTR_CONFIG not in entry_data:
                continue
            config = entry_data[ATTR_CONFIG]
            for cam_name in config.get("cameras", {}).keys():
                if cam_name not in camera_names:
                    camera_names.append(cam_name)

        camera_list = ", ".join(camera_names) if camera_names else "none detected"
        api_prompt = (
            "Frigate is a local NVR that detects objects (people, cars, animals, packages), "
            "records events, and monitors cameras. Use frigate_query for questions "
            "about activity at monitored locations — pass the user's request as-is. "
            f"Available cameras: {camera_list}."
        )

        tool = FrigateQueryTool(camera_names)

        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt,
            llm_context=llm_context,
            tools=[tool],
        )
