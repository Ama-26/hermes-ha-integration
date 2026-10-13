"""Constants for the Hermes Agent integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "hermes"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_PROFILE = "profile"
CONF_MODEL = "model"
CONF_PROVIDER = "provider"
CONF_TIMEOUT = "timeout"

# Defaults
DEFAULT_PORT = 8642
DEFAULT_PROFILE = "default"
DEFAULT_MODEL = ""  # empty = use API server default
DEFAULT_PROVIDER = ""  # empty = use API server default
DEFAULT_TIMEOUT = 60

# API paths
PATH_HEALTH = "/health"
PATH_MODELS = "/v1/models"
PATH_CAPABILITIES = "/v1/capabilities"
# Profile-scoped chat completions: /p/<profile>/v1/chat/completions
PATH_CHAT_TEMPLATE = "/p/{profile}/v1/chat/completions"

# Session continuity headers (from /v1/capabilities)
HEADER_SESSION_ID = "X-Hermes-Session-Id"
HEADER_SESSION_KEY = "X-Hermes-Session-Key"

# The API server exposes a single logical model id
MODEL_ID = "hermes-agent"

# Coordinator / polling
HEALTH_POLL_INTERVAL = 30  # seconds

# Retry logic
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt

# Conversation session map: bounded LRU of conversation_id -> server session id
MAX_SESSIONS = 64

# Response/stream byte caps (gateway-supplied data is untrusted; without a cap
# a compromised gateway could OOM the HA core by sending an endless response)
MAX_RESPONSE_BYTES = 2_000_000  # chat JSON body
MAX_SSE_LINE_BYTES = 64_000     # single SSE line
MAX_STREAM_BYTES = 10_000_000   # total SSE stream
SSE_IDLE_TIMEOUT = 30  # seconds without any socket data during a stream

# Error sensor
ERROR_CLEAR_AFTER = timedelta(hours=1)
