"""Thin async HTTP client for the Hermes Gateway API server.

The Hermes API server is OpenAI-compatible. Tool execution happens
server-side (capabilities: tool_execution == "server"), so this client only
has to forward the user's utterance and read back the assistant text.

Conversation continuity is carried by the ``X-Hermes-Session-Id`` header:
the server returns one on the first response and honours it on subsequent
requests, restoring the full conversation context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from .const import (
    HEADER_SESSION_ID,
    MODEL_ID,
    PATH_CAPABILITIES,
    PATH_CHAT_TEMPLATE,
    PATH_HEALTH,
)

_LOGGER = logging.getLogger(__name__)


class HermesApiError(Exception):
    """Raised when the Hermes API server returns an error or is unreachable."""


class HermesAuthError(HermesApiError):
    """Raised when authentication against the Hermes API server fails."""


@dataclass(slots=True)
class HermesChatResult:
    """Result of a single chat completion."""

    content: str
    session_id: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class HermesClient:
    """Async client for one Hermes API server + profile."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_key: str,
        profile: str,
        timeout: int,
        model: str = "",
    ) -> None:
        """Initialise the client.

        If ``model`` is non-empty, it is sent as the ``model`` field in the
        chat completions payload, overriding the API server's default. If
        empty, the logical model id ``hermes-agent`` is used (server picks).
        """
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._base = f"http://{host}:{port}"
        self._api_key = api_key
        self._profile = profile
        self._model = model or MODEL_ID
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def async_health(self) -> bool:
        """Return True if the API server /health endpoint responds 200."""
        try:
            async with self._session.get(
                f"{self._base}{PATH_HEALTH}",
                headers=self._auth_headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Hermes health check failed: %s", err)
            return False

    async def async_validate(self) -> None:
        """Validate connectivity + auth. Raises on failure (used by config flow)."""
        try:
            async with self._session.get(
                f"{self._base}{PATH_CAPABILITIES}",
                headers=self._auth_headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403):
                    raise HermesAuthError(f"Auth failed: HTTP {resp.status}")
                if resp.status != 200:
                    raise HermesApiError(f"Unexpected status: HTTP {resp.status}")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HermesApiError(f"Cannot reach Hermes API: {err}") from err

    async def async_chat(
        self, text: str, session_id: str | None
    ) -> HermesChatResult:
        """Send one user utterance to the profile, return the assistant reply.

        If ``session_id`` is provided it is sent back to the server to restore
        the prior conversation context. The server's returned session id is
        included in the result so the caller can persist it for the next turn.
        """
        url = f"{self._base}{PATH_CHAT_TEMPLATE.format(profile=self._profile)}"
        headers = {**self._auth_headers, "Content-Type": "application/json"}
        if session_id:
            headers[HEADER_SESSION_ID] = session_id

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": text}],
        }

        loop = _monotonic_ms()
        try:
            async with self._session.post(
                url, headers=headers, json=payload, timeout=self._timeout
            ) as resp:
                if resp.status in (401, 403):
                    raise HermesAuthError(f"Auth failed: HTTP {resp.status}")
                if resp.status != 200:
                    body = await resp.text()
                    raise HermesApiError(
                        f"Chat failed: HTTP {resp.status}: {body[:200]}"
                    )
                data = await resp.json()
                returned_sid = resp.headers.get(HEADER_SESSION_ID) or session_id
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HermesApiError(f"Chat request failed: {err}") from err

        latency_ms = _monotonic_ms() - loop

        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as err:
            raise HermesApiError(f"Malformed response: {err}") from err

        usage = data.get("usage") or {}
        return HermesChatResult(
            content=content.strip(),
            session_id=returned_sid,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )


def _monotonic_ms() -> int:
    """Return a monotonic millisecond timestamp."""
    import time

    return int(time.monotonic() * 1000)
