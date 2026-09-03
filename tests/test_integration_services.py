"""Test the frigate integration services."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest

from custom_components.frigate.const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_END_TIME,
    ATTR_START_TIME,
    SERVICE_REVIEW_SUMMARIZE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from tests import (
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
    result = await hass.services.async_call(
        "frigate",
        SERVICE_REVIEW_SUMMARIZE,
        {
            ATTR_START_TIME: start_time,
            ATTR_END_TIME: end_time,
        },
        blocking=True,
        return_response=True,
    )

    client.async_review_summarize.assert_called_with(
        datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp(),
        datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp(),
    )

    # Verify the service returns the result directly
    assert result == post_success


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


async def test_review_summarize_service_specified_instance(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service call with multiple Frigate instances."""
    client_1 = create_mock_frigate_client()
    client_1.async_review_summarize = AsyncMock(return_value={"summary": "one"})
    config_entry_1 = await setup_mock_frigate_config_entry(hass, client=client_1)

    client_2 = create_mock_frigate_client()
    client_2.async_review_summarize = AsyncMock(return_value={"summary": "two"})
    config_entry_2 = await setup_mock_frigate_config_entry(
        hass,
        config_entry=create_mock_frigate_config_entry(
            hass, entry_id="another_id", title="http://another.example.com"
        ),
        client=client_2,
    )

    start_time = "2023-09-23 13:33:44"
    end_time = "2023-09-23 18:11:22"

    for config_entry, client, expected in (
        (config_entry_1, client_1, {"summary": "one"}),
        (config_entry_2, client_2, {"summary": "two"}),
    ):
        assert (
            await hass.services.async_call(
                "frigate",
                SERVICE_REVIEW_SUMMARIZE,
                {
                    ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                    ATTR_START_TIME: start_time,
                    ATTR_END_TIME: end_time,
                },
                blocking=True,
                return_response=True,
            )
            == expected
        )
        client.async_review_summarize.assert_called_with(
            datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp(),
            datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp(),
        )


async def test_review_summarize_service_ambiguous_instance(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service call without a required instance."""
    client_1 = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client_1)

    client_2 = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(
        hass,
        config_entry=create_mock_frigate_config_entry(hass, entry_id="another_id"),
        client=client_2,
    )

    with pytest.raises(
        ServiceValidationError, match="more than one Frigate instance"
    ):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
            return_response=True,
        )

    client_1.async_review_summarize.assert_not_called()
    client_2.async_review_summarize.assert_not_called()


async def test_review_summarize_service_unknown_instance(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service call with an instance that is not loaded."""
    client = create_mock_frigate_client()
    await setup_mock_frigate_config_entry(hass, client=client)

    with pytest.raises(ServiceValidationError, match="is not loaded"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_CONFIG_ENTRY_ID: "not_a_frigate_instance",
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
            return_response=True,
        )

    client.async_review_summarize.assert_not_called()


async def test_review_summarize_service_unloaded_instance(
    hass: HomeAssistant,
) -> None:
    """Test review summarize service call when no instance is loaded."""
    client = create_mock_frigate_client()
    config_entry = await setup_mock_frigate_config_entry(hass, client=client)
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="No Frigate instance is loaded"):
        await hass.services.async_call(
            "frigate",
            SERVICE_REVIEW_SUMMARIZE,
            {
                ATTR_START_TIME: "2023-09-23 13:33:44",
                ATTR_END_TIME: "2023-09-23 18:11:22",
            },
            blocking=True,
            return_response=True,
        )

    client.async_review_summarize.assert_not_called()
