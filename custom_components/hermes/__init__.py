"""The Hermes Agent integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import HermesClient
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
from .coordinator import HermesCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.CONVERSATION,
    Platform.NOTIFY,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hermes Agent from a config entry."""
    client = HermesClient(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        api_key=entry.data[CONF_API_KEY],
        profile=entry.data.get(CONF_PROFILE, DEFAULT_PROFILE),
        timeout=entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        model=entry.options.get(
            CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL)
        ),
        provider=entry.options.get(
            CONF_PROVIDER, entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        ),
    )

    coordinator = HermesCoordinator(hass, entry, client)
    client.coordinator = coordinator
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
