"""Switch for toggling Hermes Agent session persistence."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the session persistence switch."""
    async_add_entities([HermesSessionPersistenceSwitch(entry)])


class HermesSessionPersistenceSwitch(SwitchEntity, RestoreEntity):
    """Switch to enable/disable session persistence for chat conversations."""

    _attr_has_entity_name = False
    _attr_translation_key = "session_persistence"
    _attr_name = "Hermes Session Persistence"
    _attr_icon = "mdi:chat-history"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise."""
        self._attr_unique_id = f"{entry.entry_id}_session_persistence"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )
        self._attr_is_on = True  # default: sessions persist

    async def async_added_to_hass(self) -> None:
        """Restore previous state on startup."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    @property
    def is_on(self) -> bool:
        """Return True if session persistence is enabled."""
        return self._attr_is_on or False

    async def async_turn_on(self, **kwargs) -> None:
        """Enable session persistence."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable session persistence (fresh session every request)."""
        self._attr_is_on = False
        self.async_write_ha_state()
