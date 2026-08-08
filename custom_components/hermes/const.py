"""Constants for the Hermes Agent integration."""

from __future__ import annotations

DOMAIN = "hermes"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_PROFILE = "profile"
CONF_TIMEOUT = "timeout"

# Defaults
DEFAULT_PORT = 8642
DEFAULT_PROFILE = "default"
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
