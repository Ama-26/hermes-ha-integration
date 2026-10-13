# Changelog

All notable changes to the Hermes HA Integration.

## [0.4.0] - 2026-10-13

### Security (Batch 2, audit findings C5 + C6)

- Bounded reads: chat JSON bodies capped at 2 MB, single SSE lines at 64 KB, whole SSE streams at 10 MB — a compromised gateway can no longer OOM the HA core with an endless response (abort = non-transient error, no retry). SSE streams additionally get a 30 s `sock_read` idle timeout
- Per-call stream context: session id and token usage are returned via a caller-supplied dict instead of shared client state — a concurrent notify stream can no longer overwrite the voice session's id (cross-channel session bleed race eliminated). Conversation and notify no longer touch shared mutable stream state
- Chat error bodies now read with a 4 KB cap before logging

## [0.3.2] - 2026-10-13

### Security (Audit Run 1 + Run 2: 8 confirmed findings fixed or mitigated)

- Stream retry no longer replays after the first delivered chunk — previously a mid-stream error restarted the whole request, duplicating already-delivered output, cost and token metering (docstring/code contradiction resolved; pre-chunk transient errors are now actually retried via a `transient` marker on `HermesApiError`)
- Removed active zeroconf/mDNS discovery listener (spoofing surface for API-key phishing; was documented as "dormant" but live)
- Conversation session map is now a bounded LRU (64) and no longer uses raw utterance text as session key — no unbounded memory growth, no cross-device context bleed; turns without a HA `conversation_id` get a fresh session
- `profile` config value validated against `^[A-Za-z0-9._-]{1,64}\Z` (URL-path injection hardening)
- Gateway usage fields parsed defensively (`_safe_int`: bool/None/garbage/negative tolerated, floats and numeric strings accepted); gateway error bodies sanitized before logging (`_log_safe`, 200 chars, control-char free, sliced before materialization)

### Fixed
- Stream retry: non-transient HTTP/API errors abort immediately instead of being retried (previously inconsistent between `_retry` and `_retry_stream`)

## [0.3.1] - 2026-10-10

### Fixed
- Chat stream errors now log the exception type + repr — an empty `str()` (e.g. `TimeoutError`) produced message-less log lines that cost a diagnosis round
- Conversation agent additionally catches unexpected exceptions in the chat stream/fallback path and returns the friendly error announcement instead of dying silently (pipeline death was invisible)
- Manifest version bumped to 0.3.1

## [0.3.0] - 2026-08-10

### Added
- Error binary sensor (`binary_sensor.hermes_error`) with auto-clear after 1h
- Session persistence switch (`switch.hermes_session_persistence`) with RestoreEntity
- Last interaction timestamp sensor (`sensor.hermes_last_interaction`)

### Changed
- Latency sensor now measures health endpoint round-trip directly
- API retry functions record errors for the error sensor

## [0.2.1] - 2026-08-10

### Fixed
- Latency sensor shows health endpoint round-trip time immediately, not just after chat
- Entity names now use `_attr_name` fallback when translation keys don't resolve
- Translation key nesting fixed — `entity.<platform>.<key>.name` (was incorrectly nested under domain)

## [0.2.0] - 2026-08-08

### Added
- Streaming responses via SSE (`chat_log.async_add_delta_content_stream`)
- Model auto-detection from config entry
- `notify.hermes` service for sending notifications via Hermes
- Exponential backoff retry for API calls (max 3 retries)
- Token dashboard sensors (prompt, completion, total)
- Reconfigure flow for updating host/port/model
- Diagnostics support (`get_config_entry_diagnostics`)
- Zeroconf discovery (dormant — Gateway doesn't broadcast mDNS yet)
- Device registry with icons
- Multi-profile hint in config flow description

### Changed
- Latency sensor now uses coordinator data
- Model sensor shows actual configured model, not hardcoded value
- Translation keys for all entities

## [0.1.0] - 2026-08-07

### Added
- Initial release
- Conversation agent with session support
- Binary sensor for connection status
- Latency sensor
- Model sensor
- Basic config flow (host, port, api_key, model)
