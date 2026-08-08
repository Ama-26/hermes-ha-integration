"""Conversation agent platform for Hermes Agent.

Registers a HA conversation agent that forwards each utterance to the Hermes
API server's profile-scoped chat endpoint and returns the assistant text for
TTS. Conversation context is preserved per HA conversation_id by mapping it to
a server-side Hermes session id (X-Hermes-Session-Id).

Streaming is supported via SSE — content deltas are fed into HA's chat_log
so TTS can start before the full response is generated.
"""

from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import HermesApiError
from .const import DOMAIN
from .coordinator import HermesCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Hermes conversation agent from a config entry."""
    coordinator: HermesCoordinator = entry.runtime_data
    async_add_entities([HermesConversationEntity(entry, coordinator)])


class HermesConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """A conversation agent backed by a Hermes profile."""

    _attr_has_entity_name = True
    _attr_translation_key = "hermes"
    _attr_icon = "mdi:chat-processing"
    _attr_supports_streaming = True

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise the conversation entity."""
        self._entry = entry
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hermes Gateway",
            manufacturer="Nous Research",
            model="Hermes Agent",
        )
        # Maps HA conversation_id -> Hermes server session id
        self._sessions: dict[str, str] = {}

    @property
    def supported_languages(self) -> list[str] | str:
        """Return supported languages. Hermes handles any language."""
        return conversation.MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Process a user utterance via the Hermes API.

        Uses SSE streaming via chat_log.async_add_delta_content_stream()
        so TTS can start before the full response is available.
        Falls back to non-streaming if the client doesn't support it.
        """
        conversation_id = user_input.conversation_id or user_input.text
        session_id = self._sessions.get(conversation_id)

        try:
            # Use streaming path
            stream = self._coordinator.client.async_chat_stream(
                user_input.text, session_id
            )
            content_stream = chat_log.async_add_delta_content_stream(
                self.entity_id, stream
            )
            # Consume the entire stream to get the full response
            [content async for content in content_stream]
        except HermesApiError as err:
            _LOGGER.error("Hermes chat stream failed: %s", err)
            return _error_result(
                "Ich konnte den Hermes-Agent gerade nicht erreichen.",
                user_input,
            )

        # Persist the server-side session id for conversation continuity
        if (sid := self._coordinator.client._last_stream_session_id):
            self._sessions[conversation_id] = sid

        # Push latency + connectivity to sensors
        current = self._coordinator.data or {}
        self._coordinator.async_set_updated_data(
            {
                "connected": True,
                "latency_ms": current.get("latency_ms"),
                "model": current.get("model", "hermes-agent"),
            }
        )

        return conversation.async_get_result_from_chat_log(user_input, chat_log)


def _error_result(
    message: str, user_input: conversation.ConversationInput
) -> conversation.ConversationResult:
    """Build an error conversation result."""
    response = intent.IntentResponse(language=user_input.language)
    response.async_set_error(
        intent.IntentResponseErrorCode.FAILED_TO_HANDLE, message
    )
    return conversation.ConversationResult(
        response=response, conversation_id=user_input.conversation_id
    )
