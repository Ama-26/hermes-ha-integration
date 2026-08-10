"""DataUpdateCoordinator for Hermes Agent health + status polling."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HermesClient
from .const import ERROR_CLEAR_AFTER, HEALTH_POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HermesCoordinator(DataUpdateCoordinator[dict]):
    """Polls the Hermes API server health endpoint on an interval.

    The coordinator's data dict carries the fields consumed by the sensors:
      - connected: bool
      - latency_ms: int | None   (last chat latency, updated by conversation)
      - model: str               (logical model id served)
      - prompt_tokens: int       (accumulated, reset at midnight)
      - completion_tokens: int   (accumulated, reset at midnight)
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
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._last_error: str | None = None
        self._error_count: int = 0
        self._last_error_time: datetime | None = None
        # Use the actual configured model, fall back to the logical id
        self._model = (
            entry.options.get("model")
            or entry.data.get("model")
            or "hermes-agent"
        )

    def record_latency(self, latency_ms: int) -> None:
        """Store the latency of the most recent chat completion."""
        self._last_latency_ms = latency_ms

    def record_error(self, message: str) -> None:
        """Record an API error for the error binary sensor."""
        self._last_error = message
        self._error_count += 1
        self._last_error_time = datetime.now(timezone.utc)

    def record_tokens(self, prompt: int, completion: int) -> None:
        """Accumulate token counts from a chat completion."""
        self._prompt_tokens += prompt
        self._completion_tokens += completion

    @property
    def prompt_tokens(self) -> int:
        """Accumulated prompt tokens."""
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        """Accumulated completion tokens."""
        return self._completion_tokens

    async def _async_update_data(self) -> dict:
        """Poll health; measure round-trip latency."""
        import time
        t0 = time.monotonic()
        connected = await self.client.async_health()
        health_latency = round((time.monotonic() - t0) * 1000)
        latency = self._last_latency_ms if self._last_latency_ms is not None else health_latency
        # Auto-clear error if past ERROR_CLEAR_AFTER
        error_active = self._last_error is not None
        if error_active and self._last_error_time is not None:
            if datetime.now(timezone.utc) - self._last_error_time > ERROR_CLEAR_AFTER:
                self._last_error = None
                error_active = False
        return {
            "connected": connected,
            "latency_ms": latency,
            "model": self._model,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "last_error": self._last_error,
            "error_count": self._error_count,
            "last_error_time": self._last_error_time.isoformat() if self._last_error_time else None,
            "error": error_active,
        }
