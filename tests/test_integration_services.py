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

from . import create_mock_frigate_client, setup_mock_frigate_config_entry


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

    # Verify the result is stored in hass.data
    config_entry_id = next(iter(hass.data["frigate"].keys()))
    assert "last_review_summary" in hass.data["frigate"][config_entry_id]
    assert hass.data["frigate"][config_entry_id]["last_review_summary"] == post_success


async def test_review_summarize_service_validation(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service validation."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    # Test missing start time - schema validation should catch this
    with pytest.raises(Exception, match="required"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
        )

    # Test missing end time - schema validation should catch this
    with pytest.raises(Exception, match="required"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
            },
            blocking=True,
        )

    # Test invalid datetime format
    with pytest.raises(ServiceValidationError, match="Invalid datetime format"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "invalid-date",
                ATTR_END_TIME: "2023-09-23 18:11:22",
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


async def test_review_summarize_service_version_check(
    hass: HomeAssistant,
) -> None:
    """Test that review summarize service is only registered for Frigate 0.17+."""
    # Test with version 0.16 (service should not be registered)
    config_016 = {
        "version": "0.16.0",
        "cameras": {"test": {}},
        "mqtt": {"topic_prefix": "frigate"},
    }

    client = create_mock_frigate_client()
    client.async_get_config = AsyncMock(return_value=config_016)

    # This should not register the service
    await setup_mock_frigate_config_entry(hass, client=client)

    # Verify service is not available (should not be registered for version < 0.17)
    with pytest.raises(Exception, match="service_not_found"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
        )


async def test_review_summarize_service_no_integration(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service when no Frigate integration is configured."""
    # Don't set up any Frigate integration

    # When no integration is configured, the service won't exist
    with pytest.raises(Exception, match="service_not_found"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
        )
