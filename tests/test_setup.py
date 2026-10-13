import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from custom_components.klar_assist_extensions import async_setup_entry, async_unload_entry
from custom_components.klar_assist_extensions.config_flow import ConfigFlow, validate, schema


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_can_be_disabled_without_api_client(self):
        entry=NS(data={'target_agent':'conversation.klar_nlu','weather_enabled':False},options={},
                 entry_id='test',add_update_listener=Mock(),async_on_unload=Mock())
        hass=NS(config_entries=NS(async_forward_entry_setups=AsyncMock(),async_unload_platforms=AsyncMock(return_value=True)))
        with patch('custom_components.klar_assist_extensions.async_get_clientsession') as session, patch('custom_components.klar_assist_extensions.conversation.validate_target'):
            self.assertTrue(await async_setup_entry(hass,entry))
        session.assert_not_called()
        self.assertEqual(entry.runtime_data.manager.modules,())
        self.assertTrue(await async_unload_entry(hass,entry))

    async def test_module_setup_and_reload_listener(self):
        entry=NS(data={'target_agent':'conversation.klar_nlu','weather_enabled':True,'klar_url':'http://example'},
                 options={},entry_id='test',add_update_listener=Mock(),async_on_unload=Mock())
        hass=NS(config_entries=NS(async_forward_entry_setups=AsyncMock()))
        with patch('custom_components.klar_assist_extensions.async_get_clientsession',return_value=object()), patch('custom_components.klar_assist_extensions.conversation.validate_target'):
            await async_setup_entry(hass,entry)
        self.assertEqual(entry.runtime_data.manager.modules[0].name,'weather')
        entry.add_update_listener.assert_called_once()
        entry.async_on_unload.assert_called_once()

    async def test_config_flow(self):
        flow=ConfigFlow()
        flow.hass=NS()
        with patch.object(flow,'_async_current_entries',return_value=[]), \
             patch('custom_components.klar_assist_extensions.config_flow.validate_target'):
            form=await flow.async_step_user()
            self.assertEqual(form['type'],'form')
            entry=await flow.async_step_user({'target_agent':'conversation.klar_nlu','klar_url':'http://example','weather_enabled':True})
            self.assertEqual(entry['type'],'create_entry')

    def test_config_errors(self):
        self.assertEqual(validate(NS(),{'klar_url':'file:///tmp','target_agent':'x'}),{'base':'invalid_url'})
        with patch('custom_components.klar_assist_extensions.config_flow.validate_target',side_effect=ValueError()):
            self.assertEqual(validate(NS(),{'klar_url':'http://example','target_agent':'x'}),{'base':'invalid_agent'})
        self.assertIsNotNone(schema())

    async def test_missing_target_is_configuration_error(self):
        with self.assertRaises(ConfigEntryError):
            await async_setup_entry(NS(),NS(data={},options={}))

    async def test_unavailable_target_retries_without_registration(self):
        hass=NS(config_entries=NS(async_forward_entry_setups=AsyncMock()))
        with patch('custom_components.klar_assist_extensions.conversation.validate_target',side_effect=ValueError()):
            with self.assertRaises(ConfigEntryNotReady):
                await async_setup_entry(hass,NS(data={'target_agent':'conversation.missing'},options={}))
        hass.config_entries.async_forward_entry_setups.assert_not_called()

    async def test_invalid_origin_never_creates_client(self):
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'), \
             patch('custom_components.klar_assist_extensions.async_get_clientsession') as session:
            with self.assertRaises(ConfigEntryError):
                await async_setup_entry(NS(),NS(data={'target_agent':'conversation.klar','klar_url':'file:///tmp'},options={}))
        session.assert_not_called()

    async def test_failed_platform_setup_clears_runtime_and_no_listener(self):
        entry=NS(data={'target_agent':'conversation.klar','weather_enabled':False},options={},
                 add_update_listener=Mock(),async_on_unload=Mock())
        hass=NS(config_entries=NS(async_forward_entry_setups=AsyncMock(side_effect=RuntimeError('platform error'))))
        with patch('custom_components.klar_assist_extensions.conversation.validate_target'):
            with self.assertRaises(RuntimeError):await async_setup_entry(hass,entry)
        self.assertIsNone(entry.runtime_data)
        entry.add_update_listener.assert_not_called()

    async def test_failed_unload_preserves_runtime(self):
        runtime=object()
        entry=NS(runtime_data=runtime)
        hass=NS(config_entries=NS(async_unload_platforms=AsyncMock(return_value=False)))
        self.assertFalse(await async_unload_entry(hass,entry))
        self.assertIs(entry.runtime_data,runtime)

    async def test_single_instance_config_flow_aborts(self):
        flow=ConfigFlow();flow.hass=NS()
        with patch.object(flow,'_async_current_entries',return_value=[object()]):
            result=await flow.async_step_user()
        self.assertEqual(result['reason'],'single_instance_allowed')
