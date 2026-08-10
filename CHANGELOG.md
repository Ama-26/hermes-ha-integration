# Changelog

All notable changes to the Hermes HA Integration.

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
