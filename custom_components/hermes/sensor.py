"""Sensors for Hermes Agent: latency, model, and token usage."""

from __future__ import annotations

import logging
from datetime import datetime

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
            HermesPromptTokensSensor(entry, coordinator),
            HermesCompletionTokensSensor(entry, coordinator),
            HermesTotalTokensSensor(entry, coordinator),
            HermesLastInteractionSensor(entry, coordinator),
        ]
    )


def _make_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared DeviceInfo for all sensor entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Hermes Gateway",
        manufacturer="Nous Research",
        model="Hermes Agent",
    )


class HermesLatencySensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """Last chat completion latency in milliseconds."""

    _attr_has_entity_name = False
    _attr_translation_key = "latency"
    _attr_name = "Hermes Latency"
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
        self._attr_device_info = _make_device_info(entry)

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
    _attr_name = "Hermes Model"
    _attr_icon = "mdi:robot"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_model"
        self._attr_device_info = _make_device_info(entry)

    @property
    def native_value(self) -> str | None:
        """Return the served model id."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("model")


class HermesPromptTokensSensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """Accumulated prompt tokens (since last restart)."""

    _attr_has_entity_name = False
    _attr_translation_key = "prompt_tokens"
    _attr_name = "Hermes Prompt Tokens"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_prompt_tokens"
        self._attr_device_info = _make_device_info(entry)

    @property
    def native_value(self) -> int:
        """Return accumulated prompt tokens."""
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.get("prompt_tokens", 0)


class HermesCompletionTokensSensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """Accumulated completion tokens (since last restart)."""

    _attr_has_entity_name = False
    _attr_translation_key = "completion_tokens"
    _attr_name = "Hermes Completion Tokens"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_completion_tokens"
        self._attr_device_info = _make_device_info(entry)

    @property
    def native_value(self) -> int:
        """Return accumulated completion tokens."""
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.get("completion_tokens", 0)


class HermesTotalTokensSensor(CoordinatorEntity[HermesCoordinator], SensorEntity):
    """Total prompt + completion tokens (since last restart)."""

    _attr_has_entity_name = False
    _attr_translation_key = "total_tokens"
    _attr_name = "Hermes Total Tokens"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:sigma"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total_tokens"
        self._attr_device_info = _make_device_info(entry)

    @property
    def native_value(self) -> int:
        """Return total tokens."""
        if not self.coordinator.data:
            return 0
        return (
            self.coordinator.data.get("prompt_tokens", 0)
            + self.coordinator.data.get("completion_tokens", 0)
        )


class HermesLastInteractionSensor(
    CoordinatorEntity[HermesCoordinator], SensorEntity
):
    """Timestamp of the last successful chat interaction."""

    _attr_has_entity_name = False
    _attr_translation_key = "last_interaction"
    _attr_name = "Hermes Last Interaction"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_interaction"
        self._attr_device_info = _make_device_info(entry)

    @property
    def native_value(self) -> datetime | None:
        """Return the last interaction as a datetime or None."""
        if not self.coordinator.data:
            return None
        iso = self.coordinator.data.get("last_interaction")
        if iso is None:
            return None
        try:
            return datetime.fromisoformat(iso)
        except (ValueError, TypeError):
            return None
