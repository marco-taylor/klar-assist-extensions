"""Real HA registration, flow, service and permissions in a disposable instance."""
import asyncio,json,logging,os,unittest,socket
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from aiohttp import web,ThreadedResolver,ClientSession
from homeassistant.core import HomeAssistant,Context
from homeassistant import auth,config_entries,setup,loader
from homeassistant.auth.auth_store import AuthStore
from homeassistant.auth.const import GROUP_ID_ADMIN,GROUP_ID_READ_ONLY
from homeassistant.helpers import entity_registry,device_registry
from homeassistant.components import conversation,weather
from homeassistant.components.conversation.chat_log import AssistantContent
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers import intent,aiohttp_client,frame
from homeassistant.components.homeassistant import exposed_entities
from homeassistant.const import UnitOfTemperature,UnitOfSpeed,UnitOfLength
from homeassistant.components.weather import WeatherEntity,WeatherEntityFeature
from .helpers import payload

OUTCOMES=[]
ROOT=Path(os.environ['KAE_REGISTRATION_CONFIG'])

REFERENCE_INIT='''from homeassistant.const import Platform
async def async_setup_entry(hass,entry):
 await hass.config_entries.async_forward_entry_setups(entry,[Platform.CONVERSATION])
 return True
async def async_unload_entry(hass,entry):
 return await hass.config_entries.async_unload_platforms(entry,[Platform.CONVERSATION])
'''
REFERENCE_CONVERSATION='''from homeassistant.components import conversation
from homeassistant.components.conversation.chat_log import AssistantContent
from homeassistant.helpers import intent,aiohttp_client,frame
async def async_setup_entry(hass,entry,async_add_entities):
 async_add_entities([Reference(entry)])
class Reference(conversation.ConversationEntity):
 _attr_name="Klar reference"
 _attr_supported_features=conversation.ConversationEntityFeature.CONTROL
 def __init__(self,entry):self._attr_unique_id=entry.entry_id
 @property
 def supported_languages(self):return "*"
 async def _async_handle_message(self,req,log):
  self.hass.data.setdefault("reference_calls",[]).append(req)
  response=intent.IntentResponse(language=req.language)
  response.async_set_speech("Unveränderte Referenzantwort.")
  log.async_add_assistant_content_without_tools(AssistantContent(agent_id=self.entity_id,content="Unveränderte Referenzantwort."))
  return conversation.ConversationResult(response=response,conversation_id=log.conversation_id)
'''


class TestWeather(WeatherEntity):
    _attr_should_poll=False
    _attr_supported_features=WeatherEntityFeature.FORECAST_DAILY
    _attr_native_temperature=12.2
    _attr_native_temperature_unit=UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit=UnitOfLength.MILLIMETERS
    _attr_native_wind_speed=20
    _attr_native_wind_speed_unit=UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_condition='cloudy'

    def __init__(self,name):
        self._attr_name=name
        self._attr_unique_id=name
        self.forecast_calls=0

    async def async_forecast_daily(self):
        self.forecast_calls+=1
        now=datetime.now(ZoneInfo(self.hass.config.time_zone))
        return [{'datetime':(now+timedelta(days=i)).replace(hour=12).isoformat(),'condition':'rainy',
                 'temperature':18+i,'templow':10+i,'precipitation':0,'precipitation_probability':0,
                 'humidity':70,'cloud_coverage':69,'wind_speed':20} for i in range(8)]


def entry(domain,data,title):
    return config_entries.ConfigEntry(domain=domain,data=data,options={},title=title,
        version=1,minor_version=1,source='user',unique_id=None,discovery_keys={},subentries_data=[])


class RegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=ROOT/self.id().split('.')[-1]
        self.directory.mkdir()
        # Share only this test package namespace; each HA storage remains separate.
        reference=ROOT/'custom_components/klar_nlu'
        reference.mkdir(exist_ok=True)
        (reference/'manifest.json').write_text(json.dumps({'domain':'klar_nlu','name':'Isolated Klar reference',
            'version':'1.0.0','dependencies':['conversation'],'requirements':[],'codeowners':[]}))
        (reference/'__init__.py').write_text(REFERENCE_INIT)
        (reference/'conversation.py').write_text(REFERENCE_CONVERSATION)
        (reference/'config_flow.py').write_text('''from homeassistant.config_entries import ConfigFlow
class ReferenceFlow(ConfigFlow, domain="klar_nlu"):
 VERSION=1
''')
        self.hass=HomeAssistant(str(self.directory))
        loader.async_setup(self.hass)
        frame.async_setup(self.hass)
        self.resolver=ThreadedResolver()
        self.hass.data[aiohttp_client.DATA_RESOLVER]=self.resolver
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1",0));self.port=reservation.getsockname()[1]
        self.config={"http":{"server_host":["127.0.0.1"],"server_port":self.port}}
        await self.hass.config.async_set_time_zone('Europe/Berlin')
        self.hass.config_entries=config_entries.ConfigEntries(self.hass,self.config)
        await self.hass.config_entries.async_initialize()
        self.hass.data[device_registry.DATA_REGISTRY]=device_registry.DeviceRegistry(self.hass)
        await device_registry.async_load(self.hass)
        await entity_registry.async_load(self.hass)
        self.store=AuthStore(self.hass)
        await self.store.async_load()
        self.hass.auth=auth.AuthManager(self.hass,self.store,{}, {})
        self.owner=await self.store.async_create_user('Owner',is_owner=True,is_active=True,group_ids=[GROUP_ID_ADMIN])
        self.viewer=await self.store.async_create_user('Read only',is_owner=False,is_active=True,group_ids=[GROUP_ID_READ_ONLY])
        self.denied=await self.store.async_create_user('No entity permissions',is_owner=False,is_active=True,group_ids=[])
        self.inactive=await self.store.async_create_user('Inactive',is_owner=False,is_active=False,group_ids=[])
        # Actual Home Assistant component setup and platform loader.
        self.assertTrue(await setup.async_setup_component(self.hass,'conversation',self.config))
        self.assertTrue(await setup.async_setup_component(self.hass,'weather',self.config))
        self.reference=entry('klar_nlu',{},'Klar reference')
        await self.hass.config_entries.async_add(self.reference)
        await self.hass.async_block_till_done()
        reference_entities=[s.entity_id for s in self.hass.states.async_all('conversation') if 'klar_reference' in s.entity_id]
        self.assertEqual(len(reference_entities),1)
        self.target=reference_entities[0]
        self.exposed=TestWeather('allowed_weather')
        self.hidden=TestWeather('hidden_weather')
        await self.hass.data[weather.DATA_COMPONENT].async_add_entities([self.exposed,self.hidden])
        await self.hass.async_block_till_done()
        policy=exposed_entities.ExposedEntities(self.hass)
        await policy.async_initialize()
        self.hass.data[exposed_entities.DATA_EXPOSED_ENTITIES]=policy
        policy.async_set_assistant_option('conversation',self.exposed.entity_id,'should_expose',True)
        policy.async_set_assistant_option('conversation',self.hidden.entity_id,'should_expose',False)
        self.native_calls=[]
        async def parse(req):
            body=await req.json();self.native_calls.append(body)
            selected=self.hidden.entity_id if 'hidden' in body['text'] else self.exposed.entity_id
            ask='now' if 'ist das Wetter' in body['text'] else 'tomorrow'
            return web.json_response(payload(ask,'tomorrow' if ask=='tomorrow' else '',entity=selected))
        app=web.Application();app.router.add_post('/api/v2/parse',parse)
        self.runner=web.AppRunner(app);await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.url=f'http://127.0.0.1:{port}'
        self.extension=entry('klar_assist_extensions',{'target_agent':self.target,'klar_url':self.url,'weather_enabled':True},'Extensions')
        self.before_default=conversation.async_get_agent(self.hass,None)
        await self.hass.config_entries.async_add(self.extension)
        await self.hass.async_block_till_done()
        self.agents=[s.entity_id for s in self.hass.states.async_all('conversation') if 'klar_assist_extensions' in s.entity_id]
        self.assertEqual(len(self.agents),1)
        self.agent_id=self.agents[0]

    async def asyncTearDown(self):
        if hasattr(self,'runner'):await self.runner.cleanup()
        if hasattr(self,'hass'):
            await self.hass.async_stop(force=True)
            self.hass.import_executor.shutdown(wait=True)
            await self.resolver.close()

    async def ask(self,text='Wie wird das Wetter morgen?',user=None,language='de-DE',cid='registered-test'):
        context=Context(user_id=(user or self.owner).id)
        result=await conversation.async_converse(self.hass,text,cid,context,language=language,agent_id=self.agent_id)
        return result,context

    async def test_actual_registration_does_not_replace_existing_agent(self):
        self.assertIsNotNone(conversation.async_get_agent(self.hass,self.agent_id))
        self.assertIsNotNone(conversation.async_get_agent(self.hass,self.target))
        self.assertIs(conversation.async_get_agent(self.hass,None),self.before_default)
        self.assertEqual(entity_registry.async_get(self.hass).async_get(self.agent_id).platform,'klar_assist_extensions')
        info=conversation.async_get_agent_info(self.hass,self.agent_id)
        self.assertEqual(info.id,self.agent_id)
        OUTCOMES.append({'test':'registration','agent':self.agent_id,'original':self.target,'default_unchanged':True})

    async def test_owner_forecast_through_registered_agent(self):
        result,context=await self.ask()
        self.assertIn('zwischen 11 und 19 Grad',result.response.speech['plain']['speech'])
        self.assertEqual(result.conversation_id,'registered-test')
        self.assertEqual(result.response.language,'de-DE')
        self.assertEqual(self.exposed.forecast_calls,1)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)
        OUTCOMES.append({'test':'owner_daily','response':result.response.speech,'forecast_calls':1})

    async def test_readonly_forecast_denied_without_delegate(self):
        self.assertTrue(self.viewer.permissions.check_entity(self.exposed.entity_id,'read'))
        self.assertFalse(self.viewer.permissions.check_entity(self.exposed.entity_id,'control'))
        result,_=await self.ask(user=self.viewer)
        self.assertIn('nicht verfügbar',result.response.speech['plain']['speech'])
        self.assertEqual(self.exposed.forecast_calls,0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)
        OUTCOMES.append({'test':'readonly_daily','denied':True,'forecast_execution':0,'fallback':0})

    async def test_readonly_current_weather_allowed(self):
        result,_=await self.ask('Wie ist das Wetter?',user=self.viewer)
        self.assertIn('Aktuell ist es bewölkt.',result.response.speech['plain']['speech'])
        self.assertEqual(self.exposed.forecast_calls,0)

    async def test_no_read_permission_no_data_no_fallback(self):
        self.assertFalse(self.denied.permissions.check_entity(self.exposed.entity_id,'read'))
        result,_=await self.ask(user=self.denied)
        self.assertIn('nicht verfügbar',result.response.speech['plain']['speech'])
        self.assertEqual(self.exposed.forecast_calls,0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_hidden_entity_even_owner_cannot_read_via_weather(self):
        result,_=await self.ask('Wetter hidden morgen')
        self.assertIn('nicht verfügbar',result.response.speech['plain']['speech'])
        self.assertEqual(self.hidden.forecast_calls,0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_inactive_user_never_parses_or_delegates(self):
        result,_=await self.ask('Kalender heute',user=self.inactive)
        self.assertIn('Benutzerberechtigung',result.response.speech['plain']['speech'])
        self.assertEqual(len(self.native_calls),0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_language_and_context_through_actual_delegation(self):
        for language in ['de-AT','en-US','en-GB']:
            context=Context(user_id=self.viewer.id)
            result=await conversation.async_converse(self.hass,'Kalender heute','delegate-test',context,
                language=language,agent_id=self.agent_id,device_id='test-device',satellite_id='test-satellite',extra_system_prompt='preserve')
            received=self.hass.data['reference_calls'][-1]
            self.assertIs(received.context,context)
            self.assertEqual(received.conversation_id,'delegate-test')
            self.assertEqual(received.language,language)
            self.assertEqual(received.device_id,'test-device')
            self.assertEqual(received.satellite_id,'test-satellite')
            self.assertEqual(received.extra_system_prompt,'preserve')
        self.assertEqual(len(self.native_calls),0)

    async def test_real_options_flow_and_reload_deactivate_weather(self):
        before_id=self.agent_id
        form=await self.hass.config_entries.options.async_init(self.extension.entry_id)
        self.assertEqual(form['type'],'form')
        completed=await self.hass.config_entries.options.async_configure(form['flow_id'],
            user_input={'target_agent':self.target,'klar_url':self.url,'weather_enabled':False,'klar_token':''})
        self.assertEqual(completed['type'],'create_entry')
        await self.hass.async_block_till_done()
        self.assertEqual(self.extension.runtime_data.manager.modules,())
        self.assertIsNotNone(conversation.async_get_agent(self.hass,before_id))
        self.assertIs(conversation.async_get_agent(self.hass,None),self.before_default)
        result,_=await self.ask()
        self.assertEqual(result.response.speech['plain']['speech'],'Unveränderte Referenzantwort.')
        self.assertEqual(len(self.native_calls),0)
        self.assertEqual(self.exposed.forecast_calls,0)
        OUTCOMES.append({'test':'options_reload','same_entity_id':True,'weather_disabled':True,'default_unchanged':True})

    async def test_unload_removes_only_extension(self):
        self.assertTrue(await self.hass.config_entries.async_unload(self.extension.entry_id))
        self.assertIsNone(conversation.async_get_agent(self.hass,self.agent_id))
        self.assertIsNotNone(conversation.async_get_agent(self.hass,self.target))
        self.assertIsNone(getattr(self.extension,'runtime_data',None))
        self.assertTrue(await self.hass.config_entries.async_setup(self.extension.entry_id))
        await self.hass.async_block_till_done()
        self.assertIsNotNone(conversation.async_get_agent(self.hass,self.agent_id))

    async def test_forecast_service_receives_identical_context(self):
        from homeassistant.const import EVENT_CALL_SERVICE
        events=[]
        unsubscribe=self.hass.bus.async_listen(EVENT_CALL_SERVICE,events.append)
        result,context=await self.ask()
        await self.hass.async_block_till_done()
        unsubscribe()
        weather_events=[event for event in events if event.data.get('domain')=='weather']
        self.assertEqual(len(weather_events),1)
        self.assertIs(weather_events[0].context,context)
        self.assertEqual(weather_events[0].context.user_id,self.owner.id)
        self.assertEqual(weather_events[0].context.id,context.id)
        OUTCOMES.append({'test':'same_process_context','same_object':True,'same_user_id':True,'same_context_id':True})

    async def test_public_conversation_process_service_path(self):
        context=Context(user_id=self.owner.id)
        response=await self.hass.services.async_call('conversation','process',
            {'text':'Wie wird das Wetter morgen?','agent_id':self.agent_id,'language':'de-AT','conversation_id':'service-path'},
            blocking=True,return_response=True,context=context)
        self.assertEqual(response['conversation_id'],'service-path')
        self.assertEqual(response['response']['language'],'de-AT')
        self.assertIn('zwischen 11 und 19 Grad',response['response']['speech']['plain']['speech'])
        self.assertEqual(self.exposed.forecast_calls,1)

    async def test_public_service_denied_user_never_forecasts_or_delegates(self):
        response=await self.hass.services.async_call('conversation','process',
            {'text':'Wie wird das Wetter morgen?','agent_id':self.agent_id,'language':'de-DE'},
            blocking=True,return_response=True,context=Context(user_id=self.denied.id))
        self.assertEqual(response['response']['response_type'],'error')
        self.assertEqual(self.exposed.forecast_calls,0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_backend_unreachable_is_terminal_weather_error(self):
        await self.runner.cleanup()
        result,_=await self.ask()
        self.assertEqual(result.response.response_type,intent.IntentResponseType.ERROR)
        self.assertEqual(self.exposed.forecast_calls,0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_config_flow_rejects_bad_url_and_self_target(self):
        from custom_components.klar_assist_extensions.config_flow import validate
        self.assertEqual(validate(self.hass,{'target_agent':self.target,'klar_url':'file:///etc/passwd','weather_enabled':True}),{'base':'invalid_url'})
        self.assertEqual(validate(self.hass,{'target_agent':self.agent_id,'klar_url':self.url,'weather_enabled':True}),{'base':'invalid_agent'})
        self.assertEqual(validate(self.hass,{'target_agent':self.target,'weather_enabled':False}),{})

    async def test_target_unload_does_not_fallback_to_default_agent(self):
        await self.hass.config_entries.async_unload(self.reference.entry_id)
        result,_=await self.ask('Kalender heute')
        self.assertEqual(result.response.response_type,intent.IntentResponseType.ERROR)
        self.assertIn('nicht erreichbar',result.response.speech['plain']['speech'])
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)

    async def test_missing_target_setup_is_retry_not_default_agent(self):
        from homeassistant.exceptions import ConfigEntryNotReady
        from custom_components.klar_assist_extensions import async_setup_entry
        bad=entry('klar_assist_extensions',{'target_agent':'conversation.nonexistent','weather_enabled':False},'Missing')
        with self.assertRaises(ConfigEntryNotReady):await async_setup_entry(self.hass,bad)
        self.assertIs(conversation.async_get_agent(self.hass,None),self.before_default)

    async def test_authenticated_rest_owner_and_restricted_user(self):
        # Real HA HTTP authentication and conversation view on this isolated port.
        await self.hass.http.start()
        for user, expected in [(self.owner, 'action_done'), (self.denied, 'error')]:
            refresh=await self.hass.auth.async_create_refresh_token(user,client_id='http://isolated-test')
            token=self.hass.auth.async_create_access_token(refresh)
            async with ClientSession() as session:
                async with session.post(f'http://127.0.0.1:{self.port}/api/conversation/process',
                    headers={'Authorization':f'Bearer {token}'},json={
                        'text':'Wie wird das Wetter morgen?','agent_id':self.agent_id,
                        'language':'de-DE','conversation_id':f'rest-{user.id}'}) as response:
                    body=await response.json()
                    self.assertEqual(response.status,200,body)
            self.assertEqual(body['response']['response_type'],expected)
            self.assertEqual(body['conversation_id'],f'rest-{user.id}')
        self.assertEqual(self.exposed.forecast_calls,1)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)
        OUTCOMES.append({'test':'authenticated_rest','owner_forecast':True,'restricted_denied':True})

    async def test_real_config_flow_single_instance_abort(self):
        result=await self.hass.config_entries.flow.async_init('klar_assist_extensions',context={'source':'user'})
        self.assertEqual(result['type'],'abort')
        self.assertEqual(result['reason'],'single_instance_allowed')

    async def test_real_user_flow_creates_and_registers_agent(self):
        await self.hass.config_entries.async_remove(self.extension.entry_id)
        form=await self.hass.config_entries.flow.async_init('klar_assist_extensions',context={'source':'user'})
        self.assertEqual(form['type'],'form')
        rejected=await self.hass.config_entries.flow.async_configure(form['flow_id'],user_input={
            'target_agent':self.target,'klar_url':'file:///etc/passwd','weather_enabled':True})
        self.assertEqual(rejected['errors'],{'base':'invalid_url'})
        completed=await self.hass.config_entries.flow.async_configure(form['flow_id'],user_input={
            'target_agent':self.target,'klar_url':self.url,'weather_enabled':True})
        self.assertEqual(completed['type'],'create_entry')
        await self.hass.async_block_till_done()
        entries=self.hass.config_entries.async_entries('klar_assist_extensions')
        self.assertEqual(len(entries),1)
        self.assertIsNotNone(entries[0].runtime_data)
        self.assertEqual(len([s for s in self.hass.states.async_all('conversation') if 'klar_assist_extensions' in s.entity_id]),1)
        self.assertIs(conversation.async_get_agent(self.hass,None),self.before_default)

    async def test_unknown_user_neither_parses_nor_delegates(self):
        result=await conversation.async_converse(self.hass,'Kalender heute','unknown-user',
            Context(user_id='not-an-auth-store-user'),language='de-DE',agent_id=self.agent_id)
        self.assertEqual(result.response.response_type,intent.IntentResponseType.ERROR)
        self.assertEqual(len(self.native_calls),0)
        self.assertEqual(len(self.hass.data.get('reference_calls',[])),0)
