import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from datetime import datetime
from .fixture_files import files
from .helpers import request, hass_fixture, rows, payload, TODAY
from custom_components.klar_assist_extensions.klar_client import decode_weather, KlarError
from custom_components.klar_assist_extensions.module_manager import ModuleManager
from custom_components.klar_assist_extensions.modules.weather.module import WeatherModule
from custom_components.klar_assist_extensions.modules.weather.time_parser import complete_time
from custom_components.klar_assist_extensions.modules.weather.models import WeatherQuery
from custom_components.klar_assist_extensions.modules.weather.matcher import is_candidate


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = hass_fixture()
        self.client = AsyncMock()
        self.client.weather.return_value = decode_weather(payload('tomorrow', 'tomorrow'))
        self.module = WeatherModule(self.hass, self.client, clock=lambda zone: TODAY)
        self.exposure = patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose', return_value=True)
        self.exposure.start()
        self.addCleanup(self.exposure.stop)

    async def answer(self, text, ask='today', day=''):
        self.client.weather.return_value = decode_weather(payload(ask, day))
        return (await self.module.handle(request(text))).speech

    async def test_current_uses_state_not_daily(self):
        answer = await self.answer('Wie ist das Wetter?', 'now')
        self.assertIn('Aktuell ist es teilweise bewölkt.', answer)
        self.assertIn('15 Grad', answer)
        self.assertNotIn('zwischen', answer)
        self.hass.services.async_call.assert_not_awaited()

    async def test_today_both_orders(self):
        answers = [await self.answer(text, 'today', 'today') for text in
                   ['Wie wird das Wetter heute?', 'Wie wird heute das Wetter?']]
        self.assertEqual(answers[0], answers[1])
        self.assertIn('Heute wird es', answers[0])
        self.assertIn('zwischen 10 und 18 Grad', answers[0])

    async def test_tomorrow_both_orders(self):
        answers = [await self.answer(text, 'tomorrow', 'tomorrow') for text in
                   ['Wie wird das Wetter morgen?', 'Wie wird morgen das Wetter?',
                    'Wie ist morgen das Wetter?', 'Wetter morgen']]
        self.assertEqual(len(set(answers)), 1)
        self.assertIn('Morgen wird es regnerisch.', answers[0])
        self.assertIn('zwischen 11 und 19 Grad', answers[0])

    async def test_overmorrow_all_orders_and_quotes_select_plus_two(self):
        texts = ['Wie wird das Wetter übermorgen?', 'Wie wird übermorgen das Wetter?', 'Wetter übermorgen']
        answers = []
        for text in texts:
            for suffix in ['', '“', '”', '„', '"', '   ']:
                with self.subTest(text=text, suffix=suffix):
                    ask = 'now' if text.startswith('Wetter') else 'today'
                    answers.append(await self.answer(text+suffix, ask))
                    self.assertIn('Übermorgen wird es regnerisch.', answers[-1])
                    self.assertIn('zwischen 12 und 20 Grad', answers[-1])
        self.assertEqual(len(set(answers)), 1)

    async def test_weekday(self):
        answer = await self.answer('Wetter am Donnerstag', 'today', 'thu')
        self.assertIn('Am Donnerstag', answer)
        self.assertIn('zwischen 13 und 21 Grad', answer)

    async def test_same_weekday_means_next_week(self):
        answer = await self.answer('Wetter am Montag', 'today', 'mon')
        self.assertIn('zwischen 17 und 25 Grad', answer)

    async def test_offset_numbers_and_word_orders(self):
        for text in ['Wie wird das Wetter in 3 Tagen?', 'Wie wird das Wetter in drei Tagen?',
                     'Wie wird in drei Tagen das Wetter?']:
            with self.subTest(text=text):
                answer = await self.answer(text)
                self.assertIn('In drei Tagen', answer)
                self.assertIn('zwischen 13 und 21 Grad', answer)

    async def test_compact_range_all_forms(self):
        answers = [await self.answer(text) for text in
                   ['Wie wird das Wetter die nächsten 5 Tage?',
                    'Wie wird das Wetter in den nächsten fünf Tagen?',
                    'Wetter für die nächsten 5 Tage']]
        self.assertEqual(len(set(answers)), 1)
        self.assertIn('Heute teilweise bewölkt, 10 bis 18 Grad.', answers[0])
        self.assertIn('Freitag teilweise bewölkt, 14 bis 22 Grad.', answers[0])
        self.assertNotIn('Luftfeuchtigkeit', answers[0])
        self.assertNotIn('Regenwahrscheinlichkeit', answers[0])

    async def test_rain_no_arbitrary_yes_no(self):
        answer = await self.answer('Wird es morgen regnen?', 'rain', 'tomorrow')
        self.assertIn('Morgen beträgt die Regenwahrscheinlichkeit 100 Prozent.', answer)
        self.assertIn('4,7 Millimeter', answer)
        self.assertNotIn('Ja.', answer)
        self.assertNotIn('Temperaturen', answer)

    async def test_missing_day_no_index_fallback(self):
        self.hass.services.async_call.return_value['weather.test']['forecast'] = rows()[3:]
        answer = await self.answer('Wetter übermorgen', 'now')
        self.assertEqual(answer, 'Für diesen Tag liegt noch keine Wettervorhersage vor.')

    async def test_rows_start_tomorrow_and_are_unsorted(self):
        self.hass.services.async_call.return_value['weather.test']['forecast'] = list(reversed(rows()[1:]))
        answer = await self.answer('Wetter übermorgen', 'now')
        self.assertIn('zwischen 12 und 20 Grad', answer)

    async def test_range_missing_day_is_explicit(self):
        self.hass.services.async_call.return_value['weather.test']['forecast'] = rows()[1:]
        self.assertIn('Heute: keine Vorhersage verfügbar.', await self.answer('Wetter die nächsten 2 Tage'))

    async def test_local_timezone_not_utc_date(self):
        self.module.clock = lambda zone: datetime.fromisoformat('2026-10-12T23:30:00+00:00')
        answer = await self.answer('Wetter übermorgen', 'now')
        self.assertIn('zwischen 13 und 21 Grad', answer)  # local today is October 13

    async def test_forecast_timestamp_local_date(self):
        self.hass.services.async_call.return_value['weather.test']['forecast'] = [
            {**rows()[2], 'datetime': '2026-10-13T23:30:00Z'}]
        self.assertIn('zwischen 12 und 20 Grad', await self.answer('Wetter übermorgen', 'now'))

    async def test_one_clock_snapshot(self):
        from unittest.mock import Mock
        self.module.clock = Mock(side_effect=[TODAY, datetime.fromisoformat('2026-10-13T00:00:01+02:00')])
        self.assertIn('zwischen 12 und 20 Grad', await self.answer('Wetter übermorgen', 'now'))
        self.module.clock.assert_called_once()

    async def test_synthetic_assist_quote_regression(self):
        records = json.loads(files['tests/fixtures/recorded-weather-trace.json'])
        for record in records[:6]:
            slots = record['trace'][0]['slots']
            row = record['trace'][1]['selected_forecast']
            self.hass = hass_fixture('weather.openweathermap')
            self.module.hass = self.hass
            self.hass.services.async_call.return_value = {'weather.openweathermap': {'forecast': [row]}}
            native = payload(entity='weather.openweathermap')
            native['plan']['steps'][0]['intent']['slots'] = [{'name': k, 'value': v['value']} for k, v in slots.items()]
            self.client.weather.return_value = decode_weather(native)
            answer = await self.module.handle(request(record['text']))
            self.assertEqual(answer.speech, record['trace'][1]['answer'])

    async def test_context_forwarded_exactly(self):
        from homeassistant.core import Context
        context = Context(user_id='user')
        req = request(context=context)
        await self.module.handle(req)
        self.assertIs(self.hass.services.async_call.call_args.kwargs['context'], context)
        self.hass.auth.async_get_user.assert_awaited_once_with('user')

    async def test_not_exposed_no_state_read_or_forecast(self):
        with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose', return_value=False):
            result = await self.module.handle(request())
        self.assertTrue(result.error)
        self.hass.states.get.assert_not_called()
        self.hass.services.async_call.assert_not_awaited()

    async def test_read_permission_denied(self):
        req = request(context=__import__('homeassistant.core', fromlist=['Context']).Context(user_id='restricted'))
        self.hass.auth.async_get_user.return_value.permissions.check_entity.return_value = False
        self.assertTrue((await self.module.handle(req)).error)
        self.hass.services.async_call.assert_not_awaited()

    async def test_inactive_or_unknown_user(self):
        from homeassistant.core import Context
        for user in [None, type('User', (), {'is_active': False})()]:
            self.hass.auth.async_get_user.return_value = user
            self.assertTrue((await self.module.handle(request(context=Context(user_id='x')))).error)

    async def test_service_permission_error_is_not_delegated(self):
        from homeassistant.exceptions import Unauthorized
        self.hass.services.async_call.side_effect = Unauthorized()
        result = await ModuleManager([self.module]).handle(request())
        self.assertTrue(result.error)

    async def test_unavailable_state_and_missing_forecasts(self):
        self.hass.states.get.return_value.state = 'unavailable'
        self.assertTrue((await self.module.handle(request())).error)
        self.hass.services.async_call.assert_not_awaited()
        self.hass.states.get.return_value.state = 'sunny'
        self.hass.services.async_call.return_value = {}
        self.assertIn('keine Wettervorhersage', (await self.module.handle(request())).speech)

    async def test_klar_unavailable_or_chat_is_handled_without_fallback(self):
        for err in [KlarError('unreachable'), KlarError('chat'), KlarError('schema')]:
            self.client.weather.side_effect = err
            self.assertTrue((await ModuleManager([self.module]).handle(request())).error)
            self.hass.services.async_call.assert_not_awaited()

    async def test_no_native_time_overwrite(self):
        query = decode_weather(payload('tomorrow', 'tomorrow'))
        self.assertIs(complete_time('Wetter übermorgen', query), query)

    async def test_count_bounds(self):
        for text in ['Wetter in 0 Tagen', 'Wetter in 8 Tagen', 'Wetter in 999 Tagen',
                     'Wetter in viele Tagen', 'Wetter die nächsten 0 Tage', 'Wetter die nächsten 9 Tage']:
            self.assertIn('Bitte nenne', await self.answer(text))
        for text in ['Wetter in 1 Tag', 'Wetter in sieben Tagen', 'Wetter die nächsten acht Tage']:
            self.assertNotIn('Bitte nenne', await self.answer(text))

    async def test_all_negative_regressions_zero_parse(self):
        texts = ['Schalte das Licht in drei Minuten aus.', 'Starte einen Timer für drei Tage.',
                 'Wie warm ist es im Wohnzimmer?', 'Stelle die Heizung in drei Räumen auf 20 Grad.',
                 'Was steht in drei Tagen im Kalender?', 'Öffne in zwei Minuten die Rollläden.',
                 'Ist das Licht morgen an?', 'Schalte morgen das Licht ein.',
                 'Schalte das Wohnzimmerlicht ein.', 'Wie ist der Lichtstatus?',
                 'Was steht heute im Kalender?', 'Welche Termine habe ich morgen?',
                 'Was ist am Freitag?', 'Wann ist mein nächster Termin?', 'Erzähl mir einen Witz.',
                 'Wie ist das Wetter und schalte das Licht ein.', 'Wetter im Wohnzimmer und Heizung auf 20 Grad']
        manager = ModuleManager([self.module])
        for text in texts:
            with self.subTest(text=text):
                self.assertIsNone(await manager.handle(request(text)))
        self.client.weather.assert_not_awaited()

    def test_candidate_known_weather(self):
        for text in ['Wie ist das Wetter?', 'Wie ist morgen das Wetter?', 'Wie wird morgen das Wetter?',
                     'Wird es morgen regnen?', 'Regnet es morgen?', 'Wetter am Donnerstag',
                     'Wie sieht das Wetter morgen aus?', 'Wie wird übermorgen das Wetter?“']:
            self.assertTrue(is_candidate(text, 'de-DE'), text)
        self.assertFalse(is_candidate('weather tomorrow', 'en'))

    async def test_bound_entity_used_not_hardcoded(self):
        self.hass = hass_fixture('weather.second')
        self.module.hass = self.hass
        self.client.weather.return_value = decode_weather(payload('tomorrow', 'tomorrow', entity='weather.second'))
        await self.module.handle(request())
        self.assertEqual(self.hass.services.async_call.call_args.args[2]['entity_id'], 'weather.second')

    async def test_weekday_without_weather_noun(self):
        self.assertTrue(self.module.can_handle(request('Wie wird es Donnerstag?')))
        self.assertIn('Am Donnerstag', await self.answer('Wie wird es Donnerstag?', 'today', 'thu'))

    async def test_preferred_area_from_original_device(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        registry=NS(async_get=Mock(return_value=NS(area_id='living')))
        with patch('custom_components.klar_assist_extensions.modules.weather.module.device_registry.async_get',return_value=registry):
            req=request(device_id='dev',satellite_id='sat')
            await self.module.handle(req)
        self.client.weather.assert_awaited_once_with(req,'living')

    async def test_daily_service_only_called_once(self):
        await self.answer('Wetter die nächsten 5 Tage')
        self.hass.services.async_call.assert_awaited_once()
        args=self.hass.services.async_call.call_args
        self.assertEqual(args.args[:2],('weather','get_forecasts'))
        self.assertEqual(args.args[2],{'type':'daily','entity_id':'weather.test'})
        self.assertTrue(args.kwargs['return_response'])

    async def test_unresolved_dates_do_not_silently_become_today(self):
        for text in ['Wie sieht das Wetter übermorgen aus?', 'Wetter gestern',
                     'Wetter am Donnerstag', 'Wird es übermorgen regnen?']:
            ask='rain' if 'regnen' in text else 'today'
            self.hass.services.async_call.reset_mock()
            answer=await self.answer(text,ask)
            self.assertIn('noch nicht unterstützt',answer)
            self.hass.services.async_call.assert_not_awaited()
