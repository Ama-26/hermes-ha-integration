"""Binary sensor for Hermes Agent connectivity."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HermesCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connectivity binary sensor."""
    _LOGGER.debug("binary_sensor async_setup_entry, runtime_data=%s", entry.runtime_data)
    coordinator: HermesCoordinator = entry.runtime_data
    async_add_entities([HermesConnectedBinarySensor(entry, coordinator)])


class HermesConnectedBinarySensor(
    CoordinatorEntity[HermesCoordinator], BinarySensorEntity
):
    """Reports whether the Hermes API server is reachable."""

    _attr_has_entity_name = False
    _attr_name = "Hermes Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connected"

    @property
    def is_on(self) -> bool:
        """Return True when the API server is reachable."""
        return bool(self.coordinator.data and self.coordinator.data.get("connected"))
