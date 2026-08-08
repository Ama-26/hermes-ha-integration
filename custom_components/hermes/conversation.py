"""Conversation agent platform for Hermes Agent.

Registers a HA conversation agent that forwards each utterance to the Hermes
API server's profile-scoped chat endpoint and returns the assistant text for
TTS. Conversation context is preserved per HA conversation_id by mapping it to
a server-side Hermes session id (X-Hermes-Session-Id).
"""

from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    _attr_name = "Hermes"

    def __init__(
        self, entry: ConfigEntry, coordinator: HermesCoordinator
    ) -> None:
        """Initialise the conversation entity."""
        self._entry = entry
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        # Maps HA conversation_id -> Hermes server session id
        self._sessions: dict[str, str] = {}

    @property
    def supported_languages(self) -> list[str] | str:
        """Return supported languages. Hermes handles any language."""
        return conversation.MATCH_ALL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user utterance and return the assistant response."""
        conversation_id = user_input.conversation_id or user_input.text
        session_id = self._sessions.get(conversation_id)

        try:
            result = await self._coordinator.client.async_chat(
                user_input.text, session_id
            )
        except HermesApiError as err:
            _LOGGER.error("Hermes chat failed: %s", err)
            return _error_result(
                "Ich konnte den Hermes-Agent gerade nicht erreichen.",
                user_input,
            )

        # Persist the returned session id for context on the next turn.
        if result.session_id:
            self._sessions[conversation_id] = result.session_id

        # Record latency and push to sensors immediately (don't wait for poll).
        self._coordinator.record_latency(result.latency_ms)
        current = self._coordinator.data or {}
        self._coordinator.async_set_updated_data(
            {
                "connected": current.get("connected", True),
                "latency_ms": result.latency_ms,
                "model": current.get("model", "hermes-agent"),
            }
        )

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(result.content or "")
        return conversation.ConversationResult(
            response=response,
            conversation_id=result.session_id or conversation_id,
        )


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
