"""Global fixtures for frigate component integration."""
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.plugins import (  # noqa: F401
    enable_custom_integrations,
)

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


@pytest.fixture(autouse=True)
def frigate_fixture(
    skip_notifications: Any,
    enable_custom_integrations: Any,  # noqa: F811
    hass: Any,
    mqtt_mock: MagicMock,
) -> None:
    """Automatically use an ordered combination of fixtures."""
