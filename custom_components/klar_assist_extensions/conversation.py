"""Generic module dispatch and public HA Conversation delegation."""
import asyncio
from contextvars import ContextVar
from dataclasses import replace
from homeassistant.components import conversation
from homeassistant.components.conversation.chat_log import AssistantContent
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry, intent
from .const import DOMAIN, TIMEOUT
from .module_manager import ModuleResult
from .access import active_user

_ACTIVE: ContextVar[tuple[str, ...]] = ContextVar("klar_assist_extensions_active", default=())


def validate_target(hass, target, own_id=None):
    if not isinstance(target, str) or not target.startswith("conversation.") or target == own_id:
        raise ValueError("Recursive/missing target")
    registry = entity_registry.async_get(hass)
    entry = registry.async_get(target)
    if entry is None or entry.platform != "klar_nlu" or getattr(entry, "disabled_by", None) is not None:
        raise ValueError("Target must be an official Klar conversation entity")
    agent = conversation.async_get_agent(hass, target)
    if agent is None or not getattr(agent, "available", True):
        raise ValueError("Target agent unavailable")


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ExtensionsAgent(entry)])


class ExtensionsAgent(conversation.ConversationEntity):
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL
    # Initial release promises normal responses, not nested streaming.
    _attr_supports_streaming = False
    _attr_name = "Klar Assist Extensions"

    def __init__(self, entry):
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self):
        # Non-German input is delegated unchanged; modules decide their own language.
        return "*"

    async def _reply(self, request, chat_log, result):
        response = intent.IntentResponse(language=request.language)
        if result.error:
            response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, result.speech)
        else:
            response.async_set_speech(result.speech)
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=self.entity_id, content=result.speech))
        return conversation.ConversationResult(response=response, conversation_id=chat_log.conversation_id)

    async def _async_handle_message(self, user_input, chat_log):
        # HA's ChatLog creates an id for a new conversation. Use it on both paths.
        request = replace(user_input, conversation_id=chat_log.conversation_id)
        active = _ACTIVE.get()
        if self.entity_id in active:
            return await self._reply(request, chat_log, ModuleResult("Eine rekursive Agent-Weiterleitung wurde verhindert.", True))
        token = _ACTIVE.set((*active, self.entity_id))
        try:
            if not await active_user(self.hass, request.context):
                return await self._reply(request, chat_log, ModuleResult("Die Benutzerberechtigung für diese Anfrage ist nicht verfügbar.", True))
            runtime = self.entry.runtime_data
            result = await runtime.manager.handle(request)
            if result is not None:
                return await self._reply(request, chat_log, result)
            try:
                validate_target(self.hass, runtime.target_agent, self.entity_id)
                async with asyncio.timeout(TIMEOUT):
                    return await conversation.async_converse(
                        self.hass, text=request.text, conversation_id=request.conversation_id,
                        context=request.context, language=request.language,
                        agent_id=runtime.target_agent, device_id=request.device_id,
                        satellite_id=request.satellite_id,
                        extra_system_prompt=request.extra_system_prompt)
            except (HomeAssistantError, TimeoutError, ValueError):
                return await self._reply(request, chat_log, ModuleResult("Der Klar-Agent ist gerade nicht erreichbar.", True))
        finally:
            _ACTIVE.reset(token)
