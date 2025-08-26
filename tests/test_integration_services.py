"""Test the frigate integration services."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.frigate.const import (
    ATTR_END_TIME,
    ATTR_START_TIME,
    SERVICE_REVIEW_SUMMARIZE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from . import (
    create_mock_frigate_client,
    create_mock_frigate_config_entry,
    setup_mock_frigate_config_entry,
)


async def test_review_summarize_service_call(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service call."""
    post_success = {"summary": "review_summary_data"}

    client = create_mock_frigate_client()
    client.async_review_summarize = AsyncMock(return_value=post_success)
    await setup_mock_frigate_config_entry(hass, client=client)

    start_time = "2023-09-23 13:33:44"
    end_time = "2023-09-23 18:11:22"

    # Call the service directly (not through entity)
    await hass.services.async_call(
        "frigate",
        SERVICE_REVIEW_SUMMARIZE,
        {
            ATTR_START_TIME: start_time,
            ATTR_END_TIME: end_time,
        },
        blocking=True,
    )

    client.async_review_summarize.assert_called_with(
        datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp(),
        datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp(),
    )


async def test_review_summarize_service_validation(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service validation."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    # Test empty start time
    with pytest.raises(
        ServiceValidationError, match="Start time and end time cannot be empty"
    ):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
        )

    # Test empty end time
    with pytest.raises(
        ServiceValidationError, match="Start time and end time cannot be empty"
    ):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "",
            },
            blocking=True,
        )


async def test_review_summarize_service_error_handling(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service error handling."""
    client = create_mock_frigate_client()
    client.async_review_summarize = AsyncMock(side_effect=Exception("API Error"))
    await setup_mock_frigate_config_entry(hass, client=client)

    start_time = "2023-09-23 13:33:44"
    end_time = "2023-09-23 18:11:22"

    with pytest.raises(
        ServiceValidationError, match="Review summarize failed: API Error"
    ):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: start_time,
                ATTR_END_TIME: end_time,
            },
            blocking=True,
        )
