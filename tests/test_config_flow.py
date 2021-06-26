"""Test the frigate config flow."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frigate.api import FrigateApiClientError
from custom_components.frigate.const import DOMAIN
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from . import TEST_URL, create_mock_frigate_client, create_mock_frigate_config_entry

_LOGGER = logging.getLogger(__name__)


async def test_user_success(hass: HomeAssistant) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    mock_client = create_mock_frigate_client()

    with patch(
        "custom_components.frigate.config_flow.FrigateApiClient",
        return_value=mock_client,
    ), patch(
        "custom_components.frigate.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_URL: TEST_URL,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == "example.com"
    assert result["data"] == {
        CONF_URL: TEST_URL,
    }
    assert len(mock_setup_entry.mock_calls) == 1
    assert mock_client.async_get_stats.called


async def test_user_multiple_instances(hass: HomeAssistant) -> None:
    """Test multiple instances will be allowed."""
    # Create another config for this domain.
    create_mock_frigate_config_entry(hass, entry_id="another_id")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"


async def test_user_connection_failure(hass: HomeAssistant) -> None:
    """Test connection failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    mock_client = create_mock_frigate_client()
    mock_client.async_get_stats = AsyncMock(side_effect=FrigateApiClientError)

    with patch(
        "custom_components.frigate.config_flow.FrigateApiClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_URL: TEST_URL,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


async def test_user_invalid_url(hass: HomeAssistant) -> None:
    """Test connection failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: "THIS IS NOT A URL",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_url"


async def test_duplicate(hass: HomeAssistant) -> None:
    """Test that a duplicate entry (same host) is rejected."""
    config_data = {
        CONF_URL: TEST_URL,
    }

    # Add an existing entry with the same host.
    existing_entry: MockConfigEntry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
    )
    existing_entry.add_to_hass(hass)

    # Now do the usual config entry process, and verify it is rejected.
    create_mock_frigate_config_entry(hass, data=config_data)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == "form"
    assert not result["errors"]
    mock_client = create_mock_frigate_client()

    with patch(
        "custom_components.frigate.config_flow.FrigateApiClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            config_data,
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"
