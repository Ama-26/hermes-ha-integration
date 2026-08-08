"""Config flow for the Hermes Agent integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .api import HermesApiError, HermesAuthError, HermesClient
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    CONF_PROFILE,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_PROFILE,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): str,
    }
)


class HermesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Hermes Agent."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = HermesClient(
                self.hass,
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                api_key=user_input[CONF_API_KEY],
                profile=user_input[CONF_PROFILE],
                timeout=DEFAULT_TIMEOUT,
            )
            try:
                await client.async_validate()
            except HermesAuthError:
                errors["base"] = "invalid_auth"
            except HermesApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Hermes")
                errors["base"] = "unknown"
            else:
                unique = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_PROFILE]}"
                await self.async_set_unique_id(unique)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Hermes ({user_input[CONF_PROFILE]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return HermesOptionsFlow()


class HermesOptionsFlow(OptionsFlow):
    """Options: adjust request timeout."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        schema = vol.Schema(
            {vol.Required(CONF_TIMEOUT, default=current): vol.All(int, vol.Range(min=5, max=300))}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
