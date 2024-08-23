"""Frigate HTTP views."""
from __future__ import annotations

import logging

import voluptuous as vol

from custom_components.frigate.api import FrigateApiClient, FrigateApiClientError
from custom_components.frigate.const import ATTR_WS_EVENT_PROXY, DOMAIN
from custom_components.frigate.views import (
    get_client_for_frigate_instance_id,
    get_config_entry_for_frigate_instance_id,
)
from custom_components.frigate.ws_event_proxy import WSEventProxy
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

_LOGGER: logging.Logger = logging.getLogger(__name__)


def async_setup(hass: HomeAssistant) -> None:
    """Set up the recorder websocket API."""
    websocket_api.async_register_command(hass, ws_retain_event)
    websocket_api.async_register_command(hass, ws_get_recordings)
    websocket_api.async_register_command(hass, ws_get_recordings_summary)
    websocket_api.async_register_command(hass, ws_get_events)
    websocket_api.async_register_command(hass, ws_get_events_summary)
    websocket_api.async_register_command(hass, ws_get_ptz_info)
    websocket_api.async_register_command(hass, ws_subscribe_events)
    websocket_api.async_register_command(hass, ws_unsubscribe_events)


def _get_client_or_send_error(
    hass: HomeAssistant,
    instance_id: str,
    msg_id: int,
    connection: websocket_api.ActiveConnection,
) -> FrigateApiClient | None:
    """Get the API client or send an error that it cannot be found."""
    client = get_client_for_frigate_instance_id(hass, instance_id)
    if client is None:
        connection.send_error(
            msg_id,
            websocket_api.const.ERR_NOT_FOUND,
            f"Unable to find Frigate instance with ID: {instance_id}",
        )
        return None
    return client


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/event/retain",
        vol.Required("instance_id"): str,
        vol.Required("event_id"): str,
        vol.Required("retain"): bool,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_retain_event(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Un/Retain an event."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return
    try:
        connection.send_result(
            msg["id"],
            await client.async_retain(
                msg["event_id"], msg["retain"], decode_json=False
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst un/retaining event {msg['event_id']} "
            f"for Frigate instance {msg['instance_id']}",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/recordings/get",
        vol.Required("instance_id"): str,
        vol.Required("camera"): str,
        vol.Optional("after"): int,
        vol.Optional("before"): int,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_recordings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get recordings for a camera."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return
    try:
        connection.send_result(
            msg["id"],
            await client.async_get_recordings(
                msg["camera"], msg.get("after"), msg.get("before"), decode_json=False
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst retrieving recordings for camera {msg['camera']} "
            f"for Frigate instance {msg['instance_id']}",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/recordings/summary",
        vol.Required("instance_id"): str,
        vol.Required("camera"): str,
        vol.Optional("timezone"): str,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_recordings_summary(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get recordings summary for a camera."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return
    try:
        connection.send_result(
            msg["id"],
            await client.async_get_recordings_summary(
                msg["camera"], msg.get("timezone", "utc"), decode_json=False
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst retrieving recordings summary for camera "
            f"{msg['camera']} for Frigate instance {msg['instance_id']}",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/events/get",
        vol.Required("instance_id"): str,
        vol.Optional("cameras"): [str],
        vol.Optional("labels"): [str],
        vol.Optional("sub_labels"): [str],
        vol.Optional("zones"): [str],
        vol.Optional("after"): int,
        vol.Optional("before"): int,
        vol.Optional("limit"): int,
        vol.Optional("has_clip"): bool,
        vol.Optional("has_snapshot"): bool,
        vol.Optional("favorites"): bool,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_events(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get events."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return

    try:
        connection.send_result(
            msg["id"],
            await client.async_get_events(
                msg.get("cameras"),
                msg.get("labels"),
                msg.get("sub_labels"),
                msg.get("zones"),
                msg.get("after"),
                msg.get("before"),
                msg.get("limit"),
                msg.get("has_clip"),
                msg.get("has_snapshot"),
                msg.get("favorites"),
                decode_json=False,
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst retrieving events for cameras "
            f"{msg['cameras']} for Frigate instance {msg['instance_id']}",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/events/summary",
        vol.Required("instance_id"): str,
        vol.Optional("has_clip"): bool,
        vol.Optional("has_snapshot"): bool,
        vol.Optional("timezone"): str,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_events_summary(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get events."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return

    try:
        connection.send_result(
            msg["id"],
            await client.async_get_event_summary(
                msg.get("has_clip"),
                msg.get("has_snapshot"),
                msg.get("timezone", "utc"),
                decode_json=False,
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst retrieving events summary for Frigate instance "
            f"{msg['instance_id']}",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/events/subscribe",
        vol.Required("instance_id"): str,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_subscribe_events(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Subscribe to events."""

    entry = get_config_entry_for_frigate_instance_id(hass, msg["instance_id"])
    if not entry:
        connection.send_error(
            msg["id"],
            "not_found",
            f"API error whilst subscribing to events for unknown Frigate instance "
            f"{msg['instance_id']}",
        )
        return

    event_proxy: WSEventProxy = hass.data[DOMAIN][entry.entry_id][ATTR_WS_EVENT_PROXY]
    connection.send_result(
        msg["id"], await event_proxy.subscribe(hass, msg["id"], connection)
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/events/unsubscribe",
        vol.Required("instance_id"): str,
        vol.Required("subscription_id"): int,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_unsubscribe_events(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Unsubscribe from events."""

    entry = get_config_entry_for_frigate_instance_id(hass, msg["instance_id"])
    if not entry:
        connection.send_error(
            msg["id"],
            "not_found",
            f"API error whilst unsubscribing to events for unknown Frigate instance "
            f"{msg['instance_id']}",
        )
        return

    event_proxy: WSEventProxy = hass.data[DOMAIN][entry.entry_id][ATTR_WS_EVENT_PROXY]
    if event_proxy.unsubscribe(hass, msg["subscription_id"]):
        connection.send_result(msg["id"])
    else:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "Subscription not found."
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "frigate/ptz/info",
        vol.Required("instance_id"): str,
        vol.Required("camera"): str,
    }
)  # type: ignore[misc]
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_ptz_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get PTZ info."""
    client = _get_client_or_send_error(hass, msg["instance_id"], msg["id"], connection)
    if not client:
        return

    try:
        connection.send_result(
            msg["id"],
            await client.async_get_ptz_info(
                msg["camera"],
                decode_json=False,
            ),
        )
    except FrigateApiClientError:
        connection.send_error(
            msg["id"],
            "frigate_error",
            f"API error whilst retrieving PTZ info for camera "
            f"{msg['camera']} for Frigate instance {msg['instance_id']}",
        )
