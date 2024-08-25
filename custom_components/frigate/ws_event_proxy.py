"""Frigate event proxy."""
from __future__ import annotations

import logging

from homeassistant.components import websocket_api
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)
from homeassistant.components.websocket_api import messages
from homeassistant.core import HomeAssistant

_LOGGER: logging.Logger = logging.getLogger(__name__)


class WSEventProxy:
    """Frigate event MQTT to WS proxy.

    This class subscribes to the MQTT events topic for a given Frigate topic and
    forwards the messages to a list of subscribers. MQTT payload is directly
    passed to subscribers to avoid JSON serialization/deserialization overhead
    within HA.
    """

    def __init__(self, topic_prefix: str) -> None:
        self._subscriptions: dict[int, websocket_api.ActiveConnection] = {}
        self._topics = {
            "events": {
                "topic": f"{topic_prefix}/events",
                "msg_callback": lambda msg: self._receive_message(msg),
                "qos": 0,
            }
        }
        self._sub_state = None

    async def subscribe(
        self,
        hass: HomeAssistant,
        subscription_id: int,
        connection: websocket_api.ActiveConnection,
    ) -> int:
        """Subscribe to events."""

        if self._sub_state is None:
            self._sub_state = async_prepare_subscribe_topics(
                hass, self._sub_state, self._topics
            )
            await async_subscribe_topics(hass, self._sub_state)

        # Add a callback to the websocket to unsubscribe if closed.
        connection.subscriptions[subscription_id] = lambda: self._unsubscribe_internal(
            hass, subscription_id
        )
        self._subscriptions[subscription_id] = connection
        return subscription_id

    def unsubscribe(self, hass: HomeAssistant, subscription_id: int) -> bool:
        """Unsubscribe from events."""

        if (
            subscription_id in self._subscriptions
            and subscription_id in self._subscriptions[subscription_id].subscriptions
        ):
            self._subscriptions[subscription_id].subscriptions.pop(subscription_id)
        return self._unsubscribe_internal(hass, subscription_id)

    def _unsubscribe_internal(self, hass: HomeAssistant, subscription_id: int) -> bool:
        """Unsubscribe from events.

        May be called from the websocket connection close handler. As a result
        must not change the size of connection.subscriptions which is iterated
        over in that handler.
        """

        if subscription_id not in self._subscriptions:
            return False
        self._subscriptions.pop(subscription_id)

        if not self._subscriptions:
            async_unsubscribe_topics(hass, self._sub_state)
            self._sub_state = None
        return True

    def unsubscribe_all(self, hass: HomeAssistant) -> None:
        """Unsubscribe all subscribers."""
        for subscription_id in list(self._subscriptions.keys()):
            self.unsubscribe(hass, subscription_id)

    def _receive_message(self, msg: ReceiveMessage) -> None:
        """Handle a new received MQTT message."""
        for id, connection in self._subscriptions.items():
            connection.send_message(messages.event_message(id, msg.payload))
