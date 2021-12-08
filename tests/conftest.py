"""Global fixtures for frigate component integration."""
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.plugins import (  # noqa: F401
    enable_custom_integrations,
)

from homeassistant.components.http import CONF_TRUSTED_PROXIES, CONF_USE_X_FORWARDED_FOR
from homeassistant.setup import async_setup_component

pytest_plugins = "pytest_homeassistant_custom_component"  # pylint: disable=invalid-name


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications")
def skip_notifications_fixture() -> Generator:
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield


def pytest_configure(config: Any) -> None:
    """Configure pytest to recognize custom markers."""
    config.addinivalue_line("markers", "allow_proxy: Allow trusted proxy in http setup")


@pytest.fixture(name="allow_proxy")
async def allow_proxy(request: Any, hass: Any) -> None:
    """Configure http to allow a proxy."""
    if "allow_proxy" in request.keywords:
        # Configure http component to allow proxy before any other component can
        # depend on, and load, http.
        await async_setup_component(
            hass,
            "http",
            {
                "http": {
                    CONF_USE_X_FORWARDED_FOR: True,
                    CONF_TRUSTED_PROXIES: ["127.0.0.1"],
                }
            },
        )


@pytest.fixture(autouse=True)
def frigate_fixture(
    socket_enabled: Any,
    allow_proxy: Any,
    skip_notifications: Any,
    enable_custom_integrations: Any,  # noqa: F811
    hass: Any,
    mqtt_mock: MagicMock,
) -> None:
    """Automatically use an ordered combination of fixtures."""
