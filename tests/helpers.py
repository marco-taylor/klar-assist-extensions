from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timedelta
from homeassistant.core import Context
from homeassistant.components.conversation import ConversationInput
from custom_components.klar_assist_extensions.modules.weather.models import WeatherQuery

TODAY = datetime.fromisoformat('2026-10-12T12:00:00+02:00')
UNITS = {'temperature_unit': '°C', 'precipitation_unit': 'mm', 'wind_speed_unit': 'km/h'}


def request(text='Wie wird das Wetter morgen?', **kwargs):
    return ConversationInput(text=text, context=kwargs.pop('context', Context()),
        conversation_id=kwargs.pop('conversation_id', 'isolated-session'),
        device_id=kwargs.pop('device_id', None), satellite_id=kwargs.pop('satellite_id', None),
        language=kwargs.pop('language', 'de'), agent_id='conversation.extensions', **kwargs)


def rows():
    return [{'datetime': (TODAY+timedelta(days=n)).isoformat(),
             'condition': 'rainy' if n in (1, 2) else 'partlycloudy',
             'temperature': 18+n, 'templow': 10+n,
             'precipitation': 0 if n == 0 else 4.7,
             'precipitation_probability': 0 if n == 0 else 100,
             'humidity': 76, 'cloud_coverage': 69, 'wind_speed': 22,
             'wind_gust_speed': 30} for n in range(8)]


def hass_fixture(entity='weather.test'):
    state = NS(entity_id=entity, state='partlycloudy',
               attributes={**UNITS, 'temperature': 15, 'humidity': 61, 'wind_speed': 13})
    hass = NS(config=NS(time_zone='Europe/Berlin', language='de'),
              states=NS(get=Mock(return_value=state)),
              services=NS(async_call=AsyncMock(return_value={entity: {'forecast': rows()}})),
              auth=NS(async_get_user=AsyncMock(return_value=NS(is_active=True,
                      permissions=NS(check_entity=Mock(return_value=True))))))
    return hass


def payload(ask='today', day='', entity='weather.test', part=''):
    slots = {'entity_id': entity, 'domain': 'weather', 'weather_ask': ask}
    if day:
        slots['weather_day'] = day
    if part:
        slots['weather_part'] = part
    return {'schema_version': '2.0', 'decision': {'type': 'execute'},
            'plan': {'steps': [{'intent': {'name': 'HassGetState',
              'slots': [{'name': k, 'value': v} for k, v in slots.items()]}}]}}
