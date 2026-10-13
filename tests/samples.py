"""Emit reproducible synthetic examples, clearly separate from live forecasts."""
import json
from unittest.mock import AsyncMock,patch
from .helpers import request,hass_fixture,TODAY,payload
from custom_components.klar_assist_extensions.klar_client import decode_weather
from custom_components.klar_assist_extensions.modules.weather.module import WeatherModule


async def run():
    client=AsyncMock()
    module=WeatherModule(hass_fixture(),client,clock=lambda zone:TODAY)
    report={'data_source':'synthetic forecast fixture','today':'2026-10-12','timezone':'Europe/Berlin','answers':[]}
    cases=[('Wie ist das Wetter?','now','',None),
           ('Wie wird das Wetter heute?','today','today','2026-10-12'),
           ('Wie wird morgen das Wetter?','tomorrow','tomorrow','2026-10-13'),
           ('Wie wird das Wetter übermorgen?','today','','2026-10-14'),
           ('Wie wird übermorgen das Wetter?','today','','2026-10-14'),
           ('Wetter übermorgen','now','','2026-10-14'),
           ('Wetter am Donnerstag','today','thu','2026-10-15'),
           ('Wie wird das Wetter in drei Tagen?','today','','2026-10-15'),
           ('Wetter für die nächsten fünf Tage','now','','2026-10-12 through 2026-10-16'),
           ('Wird es morgen regnen?','rain','tomorrow','2026-10-13')]
    with patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True):
        for text,ask,day,target in cases:
            client.weather.return_value=decode_weather(payload(ask,day))
            result=await module.handle(request(text))
            report['answers'].append({'text':text,'target':target,'speech':result.speech})
    print('SAMPLES_JSON='+json.dumps(report,ensure_ascii=False))
