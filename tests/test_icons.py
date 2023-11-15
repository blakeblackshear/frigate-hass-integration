"""Tests frigate icons."""

from custom_components.frigate.icons import (
    get_dynamic_icon_from_type,
    get_icon_from_switch,
    get_icon_from_type,
)


async def test_get_binary_sensor_icons() -> None:
    """Test sensor icon logic."""
    assert get_dynamic_icon_from_type("person", True) == "mdi:home"
    assert get_dynamic_icon_from_type("person", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("car", True) == "mdi:car"
    assert get_dynamic_icon_from_type("car", False) == "mdi:car-off"
    assert get_dynamic_icon_from_type("dog", True) == "mdi:dog-side"
    assert get_dynamic_icon_from_type("dog", False) == "mdi:dog-side-off"
    assert get_dynamic_icon_from_type("cat", True) == "mdi:home"
    assert get_dynamic_icon_from_type("cat", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("motorcycle", True) == "mdi:home"
    assert get_dynamic_icon_from_type("motorcycle", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("bicycle", True) == "mdi:home"
    assert get_dynamic_icon_from_type("bycicle", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("cow", True) == "mdi:home"
    assert get_dynamic_icon_from_type("cow", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("horse", True) == "mdi:home"
    assert get_dynamic_icon_from_type("horse", False) == "mdi:home-outline"
    assert get_dynamic_icon_from_type("other", True) == "mdi:home"
    assert get_dynamic_icon_from_type("other", False) == "mdi:home-outline"


async def test_get_sensor_icons() -> None:
    """Test sensor icon logic."""
    assert get_icon_from_type("person") == "mdi:human"
    assert get_icon_from_type("car") == "mdi:car"
    assert get_icon_from_type("dog") == "mdi:dog-side"
    assert get_icon_from_type("cat") == "mdi:cat"
    assert get_icon_from_type("motorcycle") == "mdi:motorbike"
    assert get_icon_from_type("bicycle") == "mdi:bicycle"
    assert get_icon_from_type("cow") == "mdi:cow"
    assert get_icon_from_type("horse") == "mdi:horse"
    assert get_icon_from_type("other") == "mdi:shield-alert"


async def test_get_switch_icons() -> None:
    """Test switch icon logic."""
    assert get_icon_from_switch("improve_contrast") == "mdi:contrast-circle"
    assert get_icon_from_switch("snapshots") == "mdi:image-multiple"
    assert get_icon_from_switch("recordings") == "mdi:filmstrip-box-multiple"
    assert get_icon_from_switch("motion") == "mdi:motion-sensor"
    assert get_icon_from_switch("ptz_autotracker") == "mdi:cctv"
