import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from homeassistant.components import conversation as ha_conversation
from homeassistant.helpers import intent
from .helpers import request
from custom_components.klar_assist_extensions.conversation import ExtensionsAgent, validate_target
from custom_components.klar_assist_extensions.module_manager import ModuleManager, ModuleResult


class ReferenceAgent(ha_conversation.AbstractConversationAgent):
    """Isolated stand-in, never the productive Klar agent."""
    supported_languages = '*'

    def __init__(self): self.calls=[]

    async def async_process(self, req):
        self.calls.append(req)
        response=intent.IntentResponse(language=req.language)
        response.async_set_speech('Unveränderte Referenzantwort.')
        return ha_conversation.ConversationResult(response=response,conversation_id=req.conversation_id,
                                                  continue_conversation=True)


def agent_fixture(manager=None):
    runtime=NS(manager=manager or ModuleManager([]),target_agent='conversation.klar_nlu')
    agent=ExtensionsAgent(NS(entry_id='test',runtime_data=runtime))
    agent.hass=NS(config=NS(language='de'),auth=NS(async_get_user=AsyncMock(return_value=NS(is_active=True))))
    agent.entity_id='conversation.extensions'
    chat_log=NS(conversation_id='isolated-session',async_add_assistant_content_without_tools=Mock())
    return agent,chat_log


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_delegate_unchanged_using_actual_ha_api(self):
        agent,chat=agent_fixture()
        target=ReferenceAgent()
        req=request('Schalte das Licht ein.',device_id='dev',satellite_id='sat',
                    language='en',extra_system_prompt='preserve')
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch('homeassistant.components.conversation.agent_manager.async_get_agent',return_value=target):
            result=await agent._async_handle_message(req,chat)
        forwarded=target.calls[0]
        for name in ['text','language','device_id','satellite_id','extra_system_prompt']:
            self.assertEqual(getattr(forwarded,name),getattr(req,name))
        self.assertIs(forwarded.context,req.context)
        self.assertEqual(forwarded.conversation_id,req.conversation_id)
        self.assertTrue(result.continue_conversation)
        self.assertEqual(result.response.speech['plain']['speech'],'Unveränderte Referenzantwort.')
        chat.async_add_assistant_content_without_tools.assert_not_called()

    async def test_new_conversation_uses_ha_chatlog_id(self):
        agent,chat=agent_fixture()
        chat.conversation_id='created-by-ha'
        req=request('Hallo',conversation_id=None)
        target=ReferenceAgent()
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch('homeassistant.components.conversation.agent_manager.async_get_agent',return_value=target):
            await agent._async_handle_message(req,chat)
        self.assertEqual(target.calls[0].conversation_id,'created-by-ha')

    async def test_claimed_module_never_calls_target(self):
        module=NS(name='weather',can_handle=Mock(return_value=True),handle=AsyncMock(return_value=ModuleResult('Übermorgen Wetter.')))
        agent,chat=agent_fixture(ModuleManager([module]))
        with patch.object(ha_conversation,'async_converse',new_callable=AsyncMock) as delegate:
            result=await agent._async_handle_message(request(),chat)
        delegate.assert_not_awaited()
        self.assertEqual(result.response.speech['plain']['speech'],'Übermorgen Wetter.')
        chat.async_add_assistant_content_without_tools.assert_called_once()

    async def test_explicit_pass_delegates(self):
        module=NS(name='future',can_handle=Mock(return_value=True),handle=AsyncMock(return_value=None))
        agent,chat=agent_fixture(ModuleManager([module]))
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch.object(ha_conversation,'async_converse',new_callable=AsyncMock) as delegate:
            await agent._async_handle_message(request('Hallo'),chat)
        delegate.assert_awaited_once()

    async def test_klar_unavailable(self):
        agent,chat=agent_fixture()
        with patch('custom_components.klar_assist_extensions.conversation.validate_target',side_effect=ValueError('gone')):
            result=await agent._async_handle_message(request('Hallo'),chat)
        self.assertIn('nicht erreichbar',result.response.speech['plain']['speech'])

    async def test_delegate_timeout(self):
        agent,chat=agent_fixture()
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch.object(ha_conversation,'async_converse',side_effect=TimeoutError()):
            result=await agent._async_handle_message(request('Hallo'),chat)
        self.assertIn('nicht erreichbar',result.response.speech['plain']['speech'])

    async def test_contextvar_reentry_guard(self):
        agent,chat=agent_fixture()
        async def recurse(*args,**kwargs): return await agent._async_handle_message(request('Hallo'),chat)
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch.object(ha_conversation,'async_converse',side_effect=recurse):
            result=await agent._async_handle_message(request('Hallo'),chat)
        self.assertIn('rekursive',result.response.speech['plain']['speech'])

    async def test_module_manager_enabled_order_and_calendar_pass(self):
        first=NS(name='future',can_handle=Mock(return_value=True),handle=AsyncMock(return_value=None))
        second=NS(name='other',can_handle=Mock(return_value=True),handle=AsyncMock(return_value=ModuleResult('Handled')))
        result=await ModuleManager([first,second]).handle(request('Kalender'))
        self.assertEqual(result.speech,'Handled')
        with self.assertRaises(ValueError): ModuleManager([first,first])
        self.assertIsNone(await ModuleManager([]).handle(request('Kalender')))

    def test_target_registry_only_official_klar(self):
        registry=NS(async_get=Mock(return_value=NS(platform='klar_nlu')))
        with patch('custom_components.klar_assist_extensions.conversation.entity_registry.async_get',return_value=registry), \
             patch.object(ha_conversation,'async_get_agent',return_value=object()):
            validate_target(NS(), 'conversation.klar_nlu','conversation.extensions')
            registry.async_get.return_value.platform='klar_assist_extensions'
            with self.assertRaises(ValueError): validate_target(NS(),'conversation.other')
            with self.assertRaises(ValueError): validate_target(NS(),'conversation.extensions','conversation.extensions')

    def test_no_klar_imports_or_llm_paths(self):
        import ast
        from .fixture_files import files
        for path,source in files.items():
            if path.startswith('custom_components/') and path.endswith('.py'):
                tree=ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node,ast.ImportFrom):
                        self.assertFalse((node.module or '').startswith('custom_components.klar_nlu'))
                    if isinstance(node,ast.Import):
                        for alias in node.names:
                            self.assertFalse(alias.name.startswith('custom_components.klar_nlu'))
                for banned in [b'/llm/',b'/speech/render',b'llama.cpp',b'engine_llm',b'async_refine_speech']:
                    self.assertNotIn(banned,source)

    def test_only_client_contains_native_slot_names(self):
        from .fixture_files import files
        for path,source in files.items():
            if path.startswith('custom_components/') and path.endswith('.py') and not path.endswith('/klar_client.py'):
                for slot in [b'weather_ask',b'weather_day',b'weather_part',b'HassGetState']:
                    self.assertNotIn(slot,source,path)


class RealConversationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        self.hass = HomeAssistant('/isolated-not-created')

    async def asyncTearDown(self):
        from homeassistant.helpers.chat_session import DATA_CHAT_SESSION_CLEANUP
        cleanup=self.hass.data.get(DATA_CHAT_SESSION_CLEANUP)
        if cleanup:
            cleanup._on_hass_stop(None)
        self.hass.import_executor.shutdown(wait=True)

    async def test_weather_through_real_ha_chat_session_and_chat_log(self):
        from .helpers import hass_fixture, TODAY, payload
        from custom_components.klar_assist_extensions.klar_client import decode_weather
        from custom_components.klar_assist_extensions.modules.weather.module import WeatherModule
        weather_hass=hass_fixture()
        client=AsyncMock()
        client.weather.return_value=decode_weather(payload())
        module=WeatherModule(weather_hass,client,clock=lambda zone:TODAY)
        agent,_=agent_fixture(ModuleManager([module]))
        agent.hass=self.hass
        texts=['Wie wird das Wetter übermorgen?', 'Wie wird übermorgen das Wetter?', 'Wetter übermorgen']
        answers=[]
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True), \
             patch.object(ha_conversation,'async_converse',new_callable=AsyncMock) as delegate:
            for text in texts:
                for suffix in ['', '“']:
                    req=request(text+suffix,conversation_id=None)
                    result=await agent.async_process(req)
                    answers.append(result.response.speech['plain']['speech'])
                    self.assertTrue(result.conversation_id)
                    self.assertEqual(client.weather.call_args.args[0].text,text+suffix)
                    self.assertEqual(client.weather.call_args.args[0].conversation_id,result.conversation_id)
        self.assertEqual(len(set(answers)),1)
        self.assertIn('Übermorgen wird es regnerisch.',answers[0])
        self.assertIn('zwischen 12 und 20 Grad',answers[0])
        delegate.assert_not_awaited()

    async def test_nested_real_entity_chatlog_has_no_duplicate_messages(self):
        from homeassistant.components.conversation.chat_log import AssistantContent, DATA_CHAT_LOGS
        class Target(ha_conversation.ConversationEntity):
            supported_languages='*'
            async def _async_handle_message(target,req,log):
                target.received=req
                response=intent.IntentResponse(language=req.language)
                response.async_set_speech('Original Klar-artige Antwort.')
                log.async_add_assistant_content_without_tools(AssistantContent(agent_id=target.entity_id,content='Original Klar-artige Antwort.'))
                return ha_conversation.ConversationResult(response=response,conversation_id=log.conversation_id)
        agent,_=agent_fixture()
        agent.hass=self.hass
        target=Target()
        target.entity_id='conversation.klar_nlu'
        target.hass=self.hass
        # Skip entity state publication only; use the actual nested chat/session APIs.
        target.internal_async_process=target.async_process
        req=request('Welche Termine habe ich morgen?',conversation_id=None)
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch('homeassistant.components.conversation.agent_manager.async_get_agent',return_value=target):
            result=await agent.async_process(req)
        content=self.hass.data[DATA_CHAT_LOGS][result.conversation_id].content
        self.assertEqual([item.role for item in content].count('user'),1)
        self.assertEqual([item.role for item in content].count('assistant'),1)
        self.assertIs(target.received.context,req.context)
        self.assertEqual(target.received.conversation_id,result.conversation_id)

    async def test_new_weather_module_receives_user_context_and_device(self):
        from homeassistant.core import Context
        module=NS(name='test',can_handle=Mock(return_value=True),handle=AsyncMock(return_value=ModuleResult('ok')))
        agent,_=agent_fixture(ModuleManager([module]))
        agent.hass=self.hass
        self.hass.auth=NS(async_get_user=AsyncMock(return_value=NS(is_active=True)))
        context=Context(user_id='test-user')
        req=request('Wetter morgen',context=context,conversation_id=None,device_id='dev',satellite_id='sat')
        result=await agent.async_process(req)
        forwarded=module.handle.call_args.args[0]
        self.assertIs(forwarded.context,context)
        self.assertEqual(forwarded.device_id,'dev')
        self.assertEqual(forwarded.satellite_id,'sat')
        self.assertEqual(forwarded.language,'de')
        self.assertEqual(forwarded.conversation_id,result.conversation_id)
