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
    CONF_MODEL,
    CONF_PORT,
    CONF_PROFILE,
    CONF_PROVIDER,
    CONF_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_PROFILE,
    DEFAULT_PROVIDER,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Known model prefix → provider mappings for auto-detection
_MODEL_PROVIDER_MAP: dict[str, str] = {
    "google/": "openrouter",
    "anthropic/": "openrouter",
    "meta-llama/": "openrouter",
    "mistralai/": "openrouter",
    "openai/": "openai",
    "deepseek/": "deepseek",
}

# Common provider choices for the dropdown
PROVIDER_OPTIONS: list[str] = [
    "openrouter",
    "openai",
    "deepseek",
    "anthropic",
    "google",
    "groq",
    "xai",
]


def _suggest_provider(model: str) -> str:
    """Auto-detect provider from model name prefix."""
    if not model:
        return ""
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if model.startswith(prefix):
            return provider
    return ""


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): str,
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
        vol.Optional(CONF_PROVIDER, default=DEFAULT_PROVIDER): vol.In(
            [""] + PROVIDER_OPTIONS
        ),
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
                model=user_input.get(CONF_MODEL, DEFAULT_MODEL),
                provider=user_input.get(CONF_PROVIDER, DEFAULT_PROVIDER),
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration (change host, port, api_key, profile)."""
        entry = self._get_reconfigure_entry()
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
                self._async_abort_entries_match(user_input)
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input, unique_id=unique
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                data_schema=STEP_USER_SCHEMA,
                suggested_values=user_input or entry.data,
            ),
            errors=errors,
        )


class HermesOptionsFlow(OptionsFlow):
    """Options: adjust timeout, model, and provider."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_timeout = self.config_entry.options.get(
            CONF_TIMEOUT, DEFAULT_TIMEOUT
        )
        current_model = self.config_entry.options.get(
            CONF_MODEL, self.config_entry.data.get(CONF_MODEL, DEFAULT_MODEL)
        )
        current_provider = self.config_entry.options.get(
            CONF_PROVIDER, self.config_entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_TIMEOUT, default=current_timeout): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
                vol.Optional(CONF_MODEL, default=current_model): str,
                vol.Optional(CONF_PROVIDER, default=current_provider): vol.In(
                    [""] + PROVIDER_OPTIONS
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
