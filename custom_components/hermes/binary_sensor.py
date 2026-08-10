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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
    async_add_entities([HermesConnectedBinarySensor(entry, coordinator), HermesErrorSensor(entry, coordinator)])


class HermesConnectedBinarySensor(
    CoordinatorEntity[HermesCoordinator], BinarySensorEntity
):
    """Reports whether the Hermes API server is reachable."""

    _attr_has_entity_name = False
    _attr_translation_key = "connected"
    _attr_name = "Hermes Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:check-network"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )

    @property
    def is_on(self) -> bool:
        """Return True when the API server is reachable."""
        return bool(self.coordinator.data and self.coordinator.data.get("connected"))


class HermesErrorSensor(
    CoordinatorEntity[HermesCoordinator], BinarySensorEntity
):
    """Binary sensor that indicates whether API errors have been recorded."""

    _attr_has_entity_name = False
    _attr_translation_key = "error"
    _attr_name = "Hermes Error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_error"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )

    @property
    def is_on(self) -> bool:
        """Return True when an error has been recorded and not yet cleared."""
        return bool(self.coordinator.data and self.coordinator.data.get("error"))

    @property
    def extra_state_attributes(self) -> dict:
        """Expose error details."""
        if not self.coordinator.data:
            return {}
        return {
            "last_error": self.coordinator.data.get("last_error"),
            "error_count": self.coordinator.data.get("error_count", 0),
            "last_error_time": self.coordinator.data.get("last_error_time"),
        }
