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
    MAX_RESPONSE_BYTES,
    MAX_RETRIES,
    MAX_SSE_LINE_BYTES,
    MAX_STREAM_BYTES,
    MODEL_ID,
    PATH_CAPABILITIES,
    PATH_CHAT_TEMPLATE,
    PATH_HEALTH,
    PATH_MODELS,
    RETRY_BASE_DELAY,
    SSE_IDLE_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce *value* to a non-negative int, tolerating None/garbage.

    Gateway-supplied usage fields are untrusted: a ``None``/string value must
    not raise, and absurd/negative values must not poison token counters.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(0, value)
    # Tolerate gateway variants that report floats ("1234.0") or numeric strings
    if isinstance(value, (float, str)):
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError, OverflowError):
            return default
    return default


def _log_safe(text: str) -> str:
    """Strip control characters from a gateway-supplied log fragment."""
    # Slice BEFORE sanitizing so an oversized body never materializes in full
    return "".join(ch if ch.isprintable() else " " for ch in text[:400])[:200]


class HermesApiError(Exception):
    """Raised when the Hermes API server returns an error or is unreachable.

    ``transient=True`` marks connection-level failures (unreachable host,
    timeouts, aborted connections) — those are the only HermesApiErrors the
    retry helpers are allowed to retry.
    """

    def __init__(self, msg, *, transient: bool = False):
        super().__init__(msg)
        self.transient = transient


class HermesAuthError(HermesApiError):
    """Raised when authentication against the Hermes API server fails."""


async def _read_bounded(resp: aiohttp.ClientResponse, cap: int) -> bytes:
    """Read the full response body, aborting when it exceeds *cap* bytes.

    A compromised gateway must not be able to OOM the HA core by sending an
    endless body — the read aborts with a non-transient HermesApiError.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in resp.content.iter_any():
        total += len(chunk)
        if total > cap:
            raise HermesApiError(f"Response body exceeded {cap} bytes — aborted")
        chunks.append(chunk)
    return b"".join(chunks)


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
        # Stream requests also abort when the server stops sending data
        self._stream_timeout = aiohttp.ClientTimeout(
            total=timeout, sock_read=SSE_IDLE_TIMEOUT
        )
        self.coordinator: object | None = None  # set by async_setup_entry

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
            self.coordinator,
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
                    body = await _read_bounded(resp, 4096)
                    raise HermesApiError(
                        f"Chat failed: HTTP {resp.status}: {_log_safe(body.decode('utf-8', 'replace'))}"
                    )
                raw = await _read_bounded(resp, MAX_RESPONSE_BYTES)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as err:
                    raise HermesApiError(
                        f"Chat response is not valid JSON: {err}"
                    ) from err
                returned_sid = resp.headers.get(HEADER_SESSION_ID) or session_id
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HermesApiError(f"Chat request failed: {err}", transient=True) from err

        latency_ms = _monotonic_ms() - loop

        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as err:
            raise HermesApiError(f"Malformed response: {err}") from err

        usage = data.get("usage") or {}
        return HermesChatResult(
            content=content.strip(),
            session_id=returned_sid,
            prompt_tokens=_safe_int(usage.get("prompt_tokens")),
            completion_tokens=_safe_int(usage.get("completion_tokens")),
            latency_ms=latency_ms,
        )

    async def async_chat_stream(
        self,
        text: str,
        session_id: str | None,
        context: dict | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Stream chat completions via SSE, yielding delta content dicts.

        Each yielded dict follows the HA delta format::

            {"content": "text chunk"}

        The caller should feed these into
        ``chat_log.async_add_delta_content_stream()``.

        The per-call *context* dict receives the stream's outcome: after the
        stream it contains ``session_id`` (the server's returned
        X-Hermes-Session-Id) and ``usage`` (token counters). Passing a
        dedicated dict per call keeps concurrent streams (voice + notify)
        from overwriting each other's session bookkeeping.
        """
        ctx = context if context is not None else {}
        async for delta in _retry_stream(
            lambda: self._async_chat_stream_raw(text, session_id, ctx),
            _LOGGER,
            "chat_stream",
            self.coordinator,
        ):
            yield delta

    async def _async_chat_stream_raw(
        self, text: str, session_id: str | None, ctx: dict
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
                url, headers=headers, json=payload, timeout=self._stream_timeout
            ) as resp:
                if resp.status in (401, 403):
                    raise HermesAuthError(f"Auth failed: HTTP {resp.status}")
                if resp.status != 200:
                    body = await _read_bounded(resp, 4096)
                    raise HermesApiError(
                        f"Chat stream failed: HTTP {resp.status}: {_log_safe(body.decode('utf-8', 'replace'))}"
                    )

                # Per-call context: the session id and usage of THIS stream go
                # into the caller-supplied dict — never into shared client
                # state, so concurrent notify/voice streams cannot bleed into
                # each other's session bookkeeping.
                ctx["session_id"] = resp.headers.get(HEADER_SESSION_ID) or session_id
                ctx["usage"] = {}

                # Parse SSE line by line with explicit byte caps. A single
                # endless line or an endless stream must not grow unbounded.
                total = 0
                while True:
                    raw_line = await resp.content.readline()
                    if not raw_line:
                        break
                    total += len(raw_line)
                    if total > MAX_STREAM_BYTES:
                        raise HermesApiError(
                            f"SSE stream exceeded {MAX_STREAM_BYTES} bytes — aborted"
                        )
                    if len(raw_line) > MAX_SSE_LINE_BYTES:
                        raise HermesApiError(
                            f"SSE line exceeded {MAX_SSE_LINE_BYTES} bytes — aborted"
                        )
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: " prefix
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        # Capture usage from last chunk
                        if "usage" in data:
                            usage = data["usage"]
                            ctx["usage"] = {
                                "prompt_tokens": _safe_int(usage.get("prompt_tokens")),
                                "completion_tokens": _safe_int(usage.get("completion_tokens")),
                            }
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
            raise HermesApiError(
                f"Chat stream failed: {type(err).__name__}: {err}", transient=True
            ) from err


def _monotonic_ms() -> int:
    """Return a monotonic millisecond timestamp."""
    import time

    return int(time.monotonic() * 1000)


async def _retry(
    fn, logger: logging.Logger, name: str, coordinator: object | None = None
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
        except HermesApiError as err:
            if not getattr(err, "transient", False):
                raise  # HTTP/API errors are not transient
            # Connection-level failure wrapped into HermesApiError — retryable
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
        except (aiohttp.ClientError, TimeoutError) as err:
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
    # All retries exhausted — record error
    msg = f"{name} failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    if coordinator is not None and hasattr(coordinator, "record_error"):
        coordinator.record_error(msg)
    raise HermesApiError(msg) from last_exc


async def _retry_stream(
    fn, logger: logging.Logger, name: str, coordinator: object | None = None
) -> AsyncGenerator[dict[str, str], None]:
    """Call a stream generator with retry on transient errors.

    Unlike ``_retry``, this wraps an async generator — if the first
    chunk arrives successfully we assume the stream is established and
    let subsequent errors propagate without retry. Once at least one
    chunk has been yielded, a failure aborts the stream instead of
    replaying (which would duplicate already-delivered content and
    incur duplicate provider cost).
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        delivered = False
        try:
            gen = fn()
            async for chunk in gen:
                delivered = True
                yield chunk
            return  # stream completed successfully
        except HermesAuthError:
            raise
        except HermesApiError as err:
            if not getattr(err, "transient", False) or delivered:
                # HTTP/API errors are not transient; transient errors after
                # content was delivered must never trigger a replay.
                raise
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
        except (aiohttp.ClientError, TimeoutError) as err:
            if delivered:
                # Stream broke after content was delivered — never replay.
                raise
            last_exc = err
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Hermes %s attempt %d/%d failed: %s. Retrying in %.1fs …",
                    name, attempt + 1, MAX_RETRIES + 1, err, delay,
                )
                await asyncio.sleep(delay)
    msg = f"{name} failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    if coordinator is not None and hasattr(coordinator, "record_error"):
        coordinator.record_error(msg)
    raise HermesApiError(
        f"{name} failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    ) from last_exc
