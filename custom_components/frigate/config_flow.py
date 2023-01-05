"""Adds config flow for Frigate."""
from __future__ import annotations

import logging
from typing import Any, Dict, cast

import voluptuous as vol
from voluptuous.validators import All, Range
from yarl import URL

from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import FrigateApiClient, FrigateApiClientError
from .const import (
    CONF_MEDIA_BROWSER_ENABLE,
    CONF_NOTIFICATION_PROXY_ENABLE,
    CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS,
    CONF_RTMP_URL_TEMPLATE,
    CONF_RTSP_URL_TEMPLATE,
    DEFAULT_HOST,
    DOMAIN,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


def get_config_entry_title(url_str: str) -> str:
    """Get the title of a config entry from the URL."""

    # Strip the scheme from the URL as it's not that interesting in the title
    # and space is limited on the integrations page.
    url = URL(url_str)
    return str(url)[len(url.scheme + "://") :]


class FrigateFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
    """Config flow for Frigate."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle a flow initialized by the user."""

        if user_input is None:
            return self._show_config_form()

        try:
            # Cannot use cv.url validation in the schema itself, so
            # apply extra validation here.
            cv.url(user_input[CONF_URL])
        except vol.Invalid:
            return self._show_config_form(user_input, errors={"base": "invalid_url"})

        try:
            session = async_create_clientsession(self.hass)
            client = FrigateApiClient(user_input[CONF_URL], session)
            await client.async_get_stats()
        except FrigateApiClientError:
            return self._show_config_form(user_input, errors={"base": "cannot_connect"})

        # Search for duplicates with the same Frigate CONF_HOST value.
        for existing_entry in self._async_current_entries(include_ignore=False):
            if existing_entry.data.get(CONF_URL) == user_input[CONF_URL]:
                return cast(
                    Dict[str, Any], self.async_abort(reason="already_configured")
                )

        return cast(
            Dict[str, Any],
            self.async_create_entry(
                title=get_config_entry_title(user_input[CONF_URL]), data=user_input
            ),
        )

    def _show_config_form(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
    ) -> dict[str, Any]:  # pylint: disable=unused-argument
        """Show the configuration form."""
        if user_input is None:
            user_input = {}

        return cast(
            Dict[str, Any],
            self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_URL, default=user_input.get(CONF_URL, DEFAULT_HOST)
                        ): str
                    }
                ),
                errors=errors,
            ),
        )

    @staticmethod
    @callback  # type: ignore[misc]
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FrigateOptionsFlowHandler:
        """Get the Hyperion Options flow."""
        return FrigateOptionsFlowHandler(config_entry)


class FrigateOptionsFlowHandler(config_entries.OptionsFlow):  # type: ignore[misc]
    """Frigate options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize a Frigate options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage the options."""
        if user_input is not None:
            return cast(
                Dict[str, Any], self.async_create_entry(title="", data=user_input)
            )

        if not self.show_advanced_options:
            return cast(
                Dict[str, Any], self.async_abort(reason="only_advanced_options")
            )

        schema: dict[Any, Any] = {
            # The input URL is not validated as being a URL to allow for the
            # possibility the template input won't be a valid URL until after
            # it's rendered.
            vol.Optional(
                CONF_RTMP_URL_TEMPLATE,
                default=self._config_entry.options.get(
                    CONF_RTMP_URL_TEMPLATE,
                    "",
                ),
            ): str,
            # The input URL is not validated as being a URL to allow for the
            # possibility the template input won't be a valid URL until after
            # it's rendered.
            vol.Optional(
                CONF_RTSP_URL_TEMPLATE,
                default=self._config_entry.options.get(
                    CONF_RTSP_URL_TEMPLATE,
                    "",
                ),
            ): str,
            vol.Optional(
                CONF_NOTIFICATION_PROXY_ENABLE,
                default=self._config_entry.options.get(
                    CONF_NOTIFICATION_PROXY_ENABLE,
                    True,
                ),
            ): bool,
            vol.Optional(
                CONF_MEDIA_BROWSER_ENABLE,
                default=self._config_entry.options.get(
                    CONF_MEDIA_BROWSER_ENABLE,
                    True,
                ),
            ): bool,
            vol.Optional(
                CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS,
                default=self._config_entry.options.get(
                    CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS,
                    0,
                ),
            ): All(int, Range(min=0)),
        }

        return cast(
            Dict[str, Any],
            self.async_show_form(step_id="init", data_schema=vol.Schema(schema)),
        )
