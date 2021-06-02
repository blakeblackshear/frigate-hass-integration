"""Global fixtures for frigate component integration."""
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.plugins import (  # noqa: F401
    enable_custom_integrations,
)

pytest_plugins = "pytest_homeassistant_custom_component"


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture() -> Generator:
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield


@pytest.fixture(name="auto_enable_custom_integrations", autouse=True)
def auto_enable_custom_integrations(
    hass: Any, enable_custom_integrations: Any  # noqa: F811
) -> None:
    """Enable custom integrations defined in the test dir."""


@pytest.fixture(name="auto_use_mqtt_mock", autouse=True)
def auto_use_mqtt_mock(
    hass: Any, mqtt_mock: MagicMock
) -> None:
    """Automatically use mqtt_mock as otherwise mqtt will fail setup."""
