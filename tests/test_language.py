"""Language routing with no translations or productive network access."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from dataclasses import replace
from homeassistant.core import Context
from .helpers import request, hass_fixture, payload, TODAY
from .test_conversation import agent_fixture, ReferenceAgent
from custom_components.klar_assist_extensions.language import normalize_language, LanguageRegistry
from custom_components.klar_assist_extensions.modules.weather.languages import LANGUAGES
from custom_components.klar_assist_extensions.modules.weather.module import WeatherModule
from custom_components.klar_assist_extensions.modules.weather.matcher import is_candidate
from custom_components.klar_assist_extensions.module_manager import ModuleManager
from custom_components.klar_assist_extensions.klar_client import decode_weather


class LanguageCodeTests(unittest.TestCase):
    def test_canonical_region_codes(self):
        for raw, canonical, primary in [('de-DE','de-DE','de'), ('de-AT','de-AT','de'),
                ('en-US','en-US','en'), ('en-GB','en-GB','en'), ('DE_at','de-AT','de'),
                (' EN_us ','en-US','en'), ('de','de','de'), ('de_CH','de-CH','de')]:
            with self.subTest(raw=raw):
                actual=normalize_language(raw)
                self.assertEqual((actual.canonical,actual.language),(canonical,primary))

    def test_script_and_variant_codes(self):
        for raw, canonical in [('sr_latn_rs','sr-Latn-RS'),('DE_latn_de','de-Latn-DE'),
                               ('en_001','en-001'),('de-DE-1996','de-DE-1996')]:
            self.assertEqual(normalize_language(raw).canonical,canonical)

    def test_invalid_or_missing_codes_do_not_default_to_german(self):
        for raw in [None,'',' ','d','de--DE','-de','de-','123','de/DE',42,'de-'+'a'*70]:
            self.assertIsNone(normalize_language(raw),raw)
            self.assertIsNone(LANGUAGES.resolve(raw),raw)

    def test_german_region_fallback_and_inactive_english(self):
        german=LANGUAGES.resolve('de')
        for code in ['de-DE','de-AT','de-CH','DE_de','de-Latn-DE']:
            self.assertIs(LANGUAGES.resolve(code),german)
        for code in ['en','en-US','en-GB','fr-FR','es-ES','xx']:
            self.assertIsNone(LANGUAGES.resolve(code))
        self.assertEqual(LANGUAGES.supported_languages,('de',))
        self.assertEqual(LANGUAGES.declared_languages,('de','en'))

    def test_registration_and_explicit_disabled_region(self):
        registry=LanguageRegistry()
        base,specific=object(),object()
        registry.register('zz',base)
        registry.register('zz-XX',specific)
        registry.register('zz-YY',None)
        self.assertIs(registry.resolve('zz-AA'),base)
        self.assertIs(registry.resolve('ZZ_xx'),specific)
        self.assertIsNone(registry.resolve('zz-YY'))
        with self.assertRaises(ValueError): registry.register('ZZ',object())
        with self.assertRaises(ValueError): registry.register('bad/tag',object())

    def test_compatibility_matcher_respects_language(self):
        for language in ['de','de-DE','de-AT','DE_de']:
            self.assertTrue(is_candidate('Wie wird übermorgen das Wetter?“',language))
        for language in ['en-US','en-GB','fr-FR','de--DE','']:
            self.assertFalse(is_candidate('Wie wird übermorgen das Wetter?“',language))


class LanguageRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass=hass_fixture()
        self.client=AsyncMock()
        self.client.weather.return_value=decode_weather(payload())
        self.module=WeatherModule(self.hass,self.client,clock=lambda zone:TODAY)

    async def test_unsupported_language_passes_without_even_running_german_matcher(self):
        provider=LANGUAGES.resolve('de')
        with patch.object(provider,'is_candidate',side_effect=AssertionError('German matcher must not run')):
            for code in ['en-US','en-GB','fr-FR','xx','de--DE']:
                req=request('Wie wird übermorgen das Wetter?',language=code)
                self.assertFalse(self.module.can_handle(req))
                self.assertIsNone(await self.module.handle(req))
                self.assertIsNone(await ModuleManager([self.module]).handle(req))
        self.client.weather.assert_not_awaited()
        self.hass.services.async_call.assert_not_awaited()

    async def test_unsupported_languages_delegated_with_original_metadata(self):
        from homeassistant.components import conversation
        agent,chat=agent_fixture(ModuleManager([self.module]))
        target=ReferenceAgent()
        for language in ['en-US','en-GB','EN_us','fr-FR','xx','de--DE']:
            context=Context(user_id='same-user')
            req=request('Wie wird übermorgen das Wetter?',language=language,context=context,
                        device_id='dev',satellite_id='sat',extra_system_prompt='preserve')
            with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
                 patch('homeassistant.components.conversation.agent_manager.async_get_agent',return_value=target):
                result=await agent._async_handle_message(req,chat)
            forwarded=target.calls[-1]
            for field in ['text','language','conversation_id','device_id','satellite_id','extra_system_prompt']:
                self.assertEqual(getattr(forwarded,field),getattr(req,field))
            self.assertIs(forwarded.context,context)
            self.assertEqual(result.response.language,language)
        self.client.weather.assert_not_awaited()
        chat.async_add_assistant_content_without_tools.assert_not_called()

    async def test_german_regional_weather_identical_in_all_orders(self):
        answers=[]
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True):
            for code in ['de','de-DE','de-AT','de_CH','DE_de']:
                for text in ['Wie wird das Wetter übermorgen?', 'Wie wird übermorgen das Wetter?', 'Wetter übermorgen?“']:
                    result=await self.module.handle(request(text,language=code))
                    answers.append(result.speech)
                    self.assertIn('Übermorgen wird es regnerisch.',result.speech)
                    self.assertIn('zwischen 12 und 20 Grad',result.speech)
                    self.assertEqual(self.client.weather.call_args.args[0].language,code)
        self.assertEqual(len(set(answers)),1)
        self.assertEqual(self.client.weather.await_count,15)
        self.assertEqual(self.hass.services.async_call.await_count,15)

    async def test_german_nonweather_pass_and_disabled_module(self):
        for code in ['de-DE','de-AT']:
            req=request('Was steht heute im Kalender?',language=code)
            self.assertIsNone(await ModuleManager([self.module]).handle(req))
            self.assertIsNone(await self.module.handle(req))
            weather=request('Wetter morgen',language=code)
            self.assertIsNone(await ModuleManager([]).handle(weather))
        self.client.weather.assert_not_awaited()

    async def test_future_provider_registered_without_changing_weather_logic(self):
        # A neutral toy provider tests the contract; not English rules/translations.
        provider=NS(code='zz',is_candidate=Mock(return_value=True),
            complete_time=Mock(side_effect=lambda text,query:replace(query,current=False,offset=2,label='TEST_LABEL')),
            format_weather=Mock(return_value='TEST_RESPONSE'),compact_day=Mock(),
            day_label=Mock(return_value='TEST_DAY'),message=Mock(return_value='TEST_MESSAGE'))
        registry=LanguageRegistry()
        registry.register('zz',provider)
        module=WeatherModule(self.hass,self.client,clock=lambda zone:TODAY,languages=registry)
        req=request('TEST_CANDIDATE',language='zz-XX')
        self.assertTrue(module.can_handle(req))
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True):
            result=await module.handle(req)
        self.assertEqual(result.speech,'TEST_RESPONSE')
        args=provider.format_weather.call_args.args
        self.assertEqual(args[0]['temperature'],20)
        self.assertEqual(args[2],'TEST_LABEL')
        self.client.weather.assert_awaited_once()

    def test_weather_core_contains_no_german_rules_or_response_text(self):
        from .fixture_files import files
        source=files['custom_components/klar_assist_extensions/modules/weather/module.py']
        for token in ['WEEKDAYS','Übermorgen','Heute','Morgen','Wettervorhersage','Regenwahrscheinlichkeit']:
            self.assertNotIn(token.encode(),source)
        self.assertIn(b'provider.complete_time',source)
        self.assertIn(b'provider.format_weather',source)

    async def test_regional_response_language_and_context_are_preserved(self):
        from homeassistant.components import conversation
        agent,chat=agent_fixture(ModuleManager([self.module]))
        context=Context(user_id='test-user')
        req=request('Wie wird übermorgen das Wetter?',language='de-AT',context=context)
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True), \
             patch.object(conversation,'async_converse',new_callable=AsyncMock) as delegate:
            result=await agent._async_handle_message(req,chat)
        delegate.assert_not_awaited()
        self.assertEqual(result.response.language,'de-AT')
        self.assertIn('Übermorgen',result.response.speech['plain']['speech'])
        self.assertIs(self.hass.services.async_call.call_args.kwargs['context'],context)

    async def test_all_german_days_and_rain_are_unchanged_for_regions(self):
        cases=[('Wie ist das Wetter?','now',''),
               ('Wie wird das Wetter heute?','today','today'),
               ('Wie wird morgen das Wetter?','tomorrow','tomorrow'),
               ('Wetter am Donnerstag','today','thu'),
               ('Wie wird das Wetter in drei Tagen?','today',''),
               ('Wetter für die nächsten fünf Tage','now',''),
               ('Wird es morgen regnen?','rain','tomorrow')]
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True):
            for text,ask,day in cases:
                self.client.weather.return_value=decode_weather(payload(ask,day))
                original=(await self.module.handle(request(text,language='de'))).speech
                for code in ['de-DE','de-AT']:
                    self.assertEqual((await self.module.handle(request(text,language=code))).speech,original)

    async def test_no_implicit_german_provider_when_registry_empty(self):
        module=WeatherModule(self.hass,self.client,languages=LanguageRegistry())
        req=request('Wetter morgen',language='de-DE')
        self.assertFalse(module.can_handle(req))
        self.assertIsNone(await module.handle(req))
        self.client.weather.assert_not_awaited()
