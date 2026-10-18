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
CONF_PREFER_LOCAL = "prefer_local_intents"

# Defaults
DEFAULT_PORT = 8642
DEFAULT_PROFILE = "default"
DEFAULT_MODEL = ""  # empty = use API server default
DEFAULT_PROVIDER = ""  # empty = use API server default
DEFAULT_TIMEOUT = 60
DEFAULT_PREFER_LOCAL = True

# Local-first intent resolution (see conversation.py)
# HA's own agent resolves exposed entities by name/alias in a few milliseconds
# and executes the intent directly — no LLM round, no server session. This is
# what makes "turn the computer plug off" a sub-second command instead of a
# multi-round agent run.
LOCAL_AGENT_ID = "conversation.home_assistant"
LOCAL_INTENT_TIMEOUT = 5.0  # seconds; local intents answer in ~50 ms
# Only a *definitive* answer may short-circuit Hermes. An error response
# ("Keine Etage mit dem Namen …") means HA did not understand the utterance and
# the request must go to Hermes instead.
LOCAL_ACCEPTED_RESPONSE_TYPES = frozenset({"action_done", "query_answer"})

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

# TLS (audit C1: Bearer key must not travel in cleartext when enabled)
CONF_USE_SSL = "use_ssl"
CONF_SSL_CERT_PATH = "ssl_cert_path"

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
