"""Sensors for Hermes Agent: latency and served model."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
    """Set up Hermes sensors."""
    _LOGGER.debug("sensor async_setup_entry, runtime_data=%s", entry.runtime_data)
    coordinator: HermesCoordinator = entry.runtime_data
    async_add_entities(
        [
            HermesLatencySensor(entry, coordinator),
            HermesModelSensor(entry, coordinator),
        ]
    )


class HermesLatencySensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """Last chat completion latency in milliseconds."""

    _attr_has_entity_name = False
    _attr_translation_key = "latency"
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_latency"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )

    @property
    def native_value(self) -> int | None:
        """Return the last recorded latency in ms."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latency_ms")


class HermesModelSensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """The logical model id served by the Hermes API."""

    _attr_has_entity_name = False
    _attr_translation_key = "model"
    _attr_icon = "mdi:robot"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_model"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )

    @property
    def native_value(self) -> str | None:
        """Return the served model id."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("model")
