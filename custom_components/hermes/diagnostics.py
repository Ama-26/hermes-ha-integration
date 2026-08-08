"""Diagnostics support for the Hermes Agent integration.

Provides download-able diagnostic data via the HA UI
(Settings → Devices & Services → Hermes → Download diagnostics).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostic data for a Hermes config entry.

    Sensitive fields (api_key) are redacted.
    """
    coordinator = entry.runtime_data
    client = coordinator.client if coordinator else None

    return {
        "integration_version": "0.2.0",
        "config": {
            "host": entry.data.get("host"),
            "port": entry.data.get("port"),
            "api_key": "***redacted***",
            "profile": entry.data.get("profile"),
            "model": entry.options.get("model", entry.data.get("model", "")),
            "provider": entry.options.get("provider", entry.data.get("provider", "")),
            "timeout": entry.options.get("timeout"),
        },
        "health": coordinator.data if coordinator else {},
        "model_id": client._model if client else None,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dict
) -> dict:
    """Return diagnostic data for a specific Hermes device."""
    return await async_get_config_entry_diagnostics(hass, entry)
