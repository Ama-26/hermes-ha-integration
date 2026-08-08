"""Notify platform for Hermes Agent — sends messages to Hermes via the API."""

from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import HermesCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Hermes notify service."""
    coordinator: HermesCoordinator = entry.runtime_data
    async_add_entities([HermesNotifyEntity(entry, coordinator)])


class HermesNotifyEntity(NotifyEntity):
    """Send messages to Hermes via the API server.

    Fire-and-forget — no session continuity. Use this from HA automations
    to notify Hermes about events (e.g. "Waschmaschine fertig").
    """

    _attr_has_entity_name = True
    _attr_translation_key = "notify"
    _attr_icon = "mdi:message-alert"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__()
        self._entry = entry
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a notification message to Hermes.

        Posts a single chat completion to the profile-scoped endpoint.
        No session continuity — each call is independent.
        """
        text = f"{title}: {message}" if title else message
        try:
            async for _ in self._coordinator.client.async_chat_stream(
                text, session_id=None
            ):
                pass  # Consume the stream; we don't need the response
        except Exception:
            _LOGGER.exception("Failed to send Hermes notification")
