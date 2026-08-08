"""Thin async HTTP client for the Hermes Gateway API server.

The Hermes API server is OpenAI-compatible. Tool execution happens
server-side (capabilities: tool_execution == "server"), so this client only
has to forward the user's utterance and read back the assistant text.

Conversation continuity is carried by the ``X-Hermes-Session-Id`` header:
the server returns one on the first response and honours it on subsequent
requests, restoring the full conversation context.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from .const import (
    HEADER_SESSION_ID,
    MAX_RETRIES,
    MODEL_ID,
    PATH_CAPABILITIES,
    PATH_CHAT_TEMPLATE,
    PATH_HEALTH,
    PATH_MODELS,
    RETRY_BASE_DELAY,
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
        provider: str = "",
    ) -> None:
        """Initialise the client.

        If ``model`` is non-empty, it is sent as the ``model`` field in the
        chat completions payload, overriding the API server's default. When
        ``provider`` is also set, the API server routes to that provider
        directly — required when the model name belongs to a different
        provider than the gateway default.

        If both are empty, the logical model id ``hermes-agent`` is used
        (server picks its configured default).
        """
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._base = f"http://{host}:{port}"
        self._api_key = api_key
        self._profile = profile
        self._model = model or MODEL_ID
        self._provider = provider
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._last_stream_session_id: str | None = None

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

    async def async_get_models(self) -> list[str]:
        """Fetch available model names from the API server.

        Returns the list of model ids from ``GET /v1/models``.
        Returns an empty list if the endpoint is unreachable.
        """
        try:
            async with self._session.get(
                f"{self._base}{PATH_MODELS}",
                headers=self._auth_headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as err:
            _LOGGER.debug("Failed to fetch models: %s", err)
            return []

    async def async_chat(
        self, text: str, session_id: str | None
    ) -> HermesChatResult:
        """Send one user utterance to the profile, return the assistant reply.

        If ``session_id`` is provided it is sent back to the server to restore
        the prior conversation context. The server's returned session id is
        included in the result so the caller can persist it for the next turn.
        """
        return await _retry(
            lambda: self._async_chat_raw(text, session_id),
            _LOGGER,
            "chat",
        )

    async def _async_chat_raw(
        self, text: str, session_id: str | None
    ) -> HermesChatResult:
        url = f"{self._base}{PATH_CHAT_TEMPLATE.format(profile=self._profile)}"
        headers = {**self._auth_headers, "Content-Type": "application/json"}
        if session_id:
            headers[HEADER_SESSION_ID] = session_id

        payload: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": text}],
        }
        if self._provider:
            payload["provider"] = self._provider

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

    async def async_chat_stream(
        self, text: str, session_id: str | None
    ) -> AsyncGenerator[dict[str, str], None]:
        """Stream chat completions via SSE, yielding delta content dicts.

        Each yielded dict follows the HA delta format::

            {"content": "text chunk"}

        The caller should feed these into
        ``chat_log.async_add_delta_content_stream()``.

        The returned X-Hermes-Session-Id header is stored in
        ``self._last_stream_session_id`` for the caller to use in
        subsequent turns.
        """
        async for delta in _retry_stream(
            lambda: self._async_chat_stream_raw(text, session_id),
            _LOGGER,
            "chat_stream",
        ):
            yield delta

    async def _async_chat_stream_raw(
        self, text: str, session_id: str | None
    ) -> AsyncGenerator[dict[str, str], None]:
        url = f"{self._base}{PATH_CHAT_TEMPLATE.format(profile=self._profile)}"
        headers = {
            **self._auth_headers,
            "Content-Type": "application/json",
        }
        if session_id:
            headers[HEADER_SESSION_ID] = session_id

        payload: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": text}],
            "stream": True,
        }
        if self._provider:
            payload["provider"] = self._provider

        try:
            async with self._session.post(
                url, headers=headers, json=payload, timeout=self._timeout
            ) as resp:
                if resp.status in (401, 403):
                    raise HermesAuthError(f"Auth failed: HTTP {resp.status}")
                if resp.status != 200:
                    body = await resp.text()
                    raise HermesApiError(
                        f"Chat stream failed: HTTP {resp.status}: {body[:200]}"
                    )

                # Capture the session id from response headers for continuity
                self._last_stream_session_id = resp.headers.get(HEADER_SESSION_ID) or session_id

                # Parse SSE: data: {...}\n\n
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: " prefix
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield {"content": content}
                    except json.JSONDecodeError:
                        _LOGGER.debug("SSE parse error: %s", data_str[:100])
                        continue
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HermesApiError(f"Chat stream failed: {err}") from err


def _monotonic_ms() -> int:
    """Return a monotonic millisecond timestamp."""
    import time

    return int(time.monotonic() * 1000)


async def _retry(
    fn, logger: logging.Logger, name: str
) -> HermesChatResult:
    """Call *fn* with exponential backoff on transient errors.

    Only retries on ``aiohttp.ClientError`` and ``TimeoutError``.
    HTTP errors (4xx, 5xx) and ``HermesApiError`` are raised immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await fn()
        except HermesAuthError:
            raise  # Auth errors are never transient
        except HermesApiError:
            raise  # HTTP/API errors are not transient
        except (aiohttp.ClientError, TimeoutError) as err:
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
    raise HermesApiError(
        f"{name} failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    ) from last_exc


async def _retry_stream(
    fn, logger: logging.Logger, name: str
) -> AsyncGenerator[dict[str, str], None]:
    """Call a stream generator with retry on transient errors.

    Unlike ``_retry``, this wraps an async generator — if the first
    chunk arrives successfully we assume the stream is established and
    let subsequent errors propagate without retry.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            gen = fn()
            async for chunk in gen:
                yield chunk
            return  # stream completed successfully
        except HermesAuthError:
            raise
        except HermesApiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
    raise HermesApiError(
        f"{name} failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    ) from last_exc
