"""Isolated full HA Conversation benchmark; reference agent/API, never live Klar."""
import asyncio, json, statistics, time
from unittest.mock import Mock, patch
from aiohttp import web, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.chat_session import DATA_CHAT_SESSION_CLEANUP
from homeassistant.components import conversation as ha_conversation
from homeassistant.components.conversation.chat_log import AssistantContent
from custom_components.klar_assist_extensions.klar_client import KlarClient
from custom_components.klar_assist_extensions.modules.weather.module import WeatherModule
from custom_components.klar_assist_extensions.module_manager import ModuleManager
from .helpers import request, hass_fixture, payload, TODAY
from .test_conversation import agent_fixture


class ReferenceEntity(ha_conversation.ConversationEntity):
    supported_languages='*'

    async def _async_handle_message(self, req, log):
        response=intent.IntentResponse(language=req.language)
        response.async_set_speech('Unveränderte Referenzantwort.')
        log.async_add_assistant_content_without_tools(AssistantContent(agent_id=self.entity_id,content='Unveränderte Referenzantwort.'))
        return ha_conversation.ConversationResult(response=response,conversation_id=log.conversation_id)


async def run():
    calls=0
    async def parse(req):
        nonlocal calls
        await req.json()
        calls+=1
        return web.json_response(payload())
    app=web.Application()
    app.router.add_post('/api/v2/parse',parse)
    runner=web.AppRunner(app)
    await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    port=site._server.sockets[0].getsockname()[1]
    hass=HomeAssistant('/isolated-not-created')
    try:
        async with ClientSession() as session:
            module=WeatherModule(hass_fixture(),KlarClient(session,f'http://127.0.0.1:{port}'),clock=lambda zone:TODAY)
            agent,_=agent_fixture(ModuleManager([module]))
            agent.hass=hass
            agent.async_write_ha_state=Mock()  # no registered entities, no state publication
            target=ReferenceEntity()
            target.hass=hass
            target.entity_id='conversation.klar_nlu'
            target.async_write_ha_state=Mock()
            def select(hass,agent_id=None):
                return agent if agent_id=='conversation.extensions' else target
            nonweather=request('Schalte das Wohnzimmerlicht ein.',conversation_id=None)
            weather=request('Wie wird übermorgen das Wetter?',conversation_id=None)
            async def call(req,agent_id):
                return await ha_conversation.async_converse(hass,req.text,
                    req.conversation_id,req.context,language=req.language,agent_id=agent_id)
            report={'environment':'isolated Python process; actual HA ConversationEntity/ChatSession/ChatLog/public delegation; reference Klar entity; loopback parse API fixture; forecast fixture',
                    'live_klar_benchmark':False,'repetitions':500,'warmup':30,'results':{}}
            with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
                 patch('homeassistant.components.conversation.agent_manager.async_get_agent',side_effect=select), \
                 patch('custom_components.klar_assist_extensions.modules.weather.module.async_should_expose',return_value=True):
                for name,req,agent_id in [('A_direct_reference_agent',nonweather,'conversation.klar_nlu'),
                        ('B_extensions_nonweather',nonweather,'conversation.extensions'),
                        ('C_extensions_weather',weather,'conversation.extensions')]:
                    for _ in range(30): await call(req,agent_id)
                    before=calls
                    timings=[]
                    for _ in range(500):
                        start=time.perf_counter_ns()
                        await call(req,agent_id)
                        timings.append((time.perf_counter_ns()-start)/1e6)
                    report['results'][name]={'median_ms':round(statistics.median(timings),4),
                                            'p95_ms':round(sorted(timings)[474],4),
                                            'parse_http_calls':calls-before}
            print('BENCHMARK_JSON='+json.dumps(report,ensure_ascii=False))
    finally:
        if cleanup:=hass.data.get(DATA_CHAT_SESSION_CLEANUP):
            cleanup._on_hass_stop(None)
        hass.import_executor.shutdown(wait=True)
        await runner.cleanup()
