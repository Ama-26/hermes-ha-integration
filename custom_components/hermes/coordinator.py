"""DataUpdateCoordinator for Hermes Agent health + status polling."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HermesClient
from .const import HEALTH_POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HermesCoordinator(DataUpdateCoordinator[dict]):
    """Polls the Hermes API server health endpoint on an interval.

    The coordinator's data dict carries the fields consumed by the sensors:
      - connected: bool
      - latency_ms: int | None   (last chat latency, updated by conversation)
      - model: str               (logical model id served)
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: HermesClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="hermes",
            update_interval=timedelta(seconds=HEALTH_POLL_INTERVAL),
        )
        self.client = client
        self.entry = entry
        self._last_latency_ms: int | None = None

    def record_latency(self, latency_ms: int) -> None:
        """Store the latency of the most recent chat completion."""
        self._last_latency_ms = latency_ms

    async def _async_update_data(self) -> dict:
        """Poll health; never raise so the integration stays alive when down."""
        connected = await self.client.async_health()
        return {
            "connected": connected,
            "latency_ms": self._last_latency_ms,
            "model": "hermes-agent",
        }
