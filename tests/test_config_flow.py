"""Test the frigate config flow."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.frigate.const import DOMAIN, NAME

from . import TEST_HOST, create_mock_frigate_client, create_mock_frigate_config_entry

_LOGGER = logging.getLogger(__package__)


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
                CONF_HOST: TEST_HOST,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == NAME
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
    }
    assert len(mock_setup_entry.mock_calls) == 1
    assert mock_client.async_get_stats.called


async def test_user_multiple_instances(hass: HomeAssistant) -> None:
    """Test multiple instances."""
    # Create another config for this domain.
    create_mock_frigate_config_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


async def test_user_connection_failure(hass: HomeAssistant) -> None:
    """Test connection failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    mock_client = create_mock_frigate_client()
    mock_client.async_get_stats = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch(
        "custom_components.frigate.config_flow.FrigateApiClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: TEST_HOST,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"
