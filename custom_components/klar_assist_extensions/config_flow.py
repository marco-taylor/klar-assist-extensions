"""Explicit agent/API configuration; never read Klar's private config storage."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_AGENT, CONF_URL, CONF_TOKEN, CONF_WEATHER
from .klar_client import valid_url
from .conversation import validate_target


def schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_AGENT, default=defaults.get(CONF_AGENT, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="conversation", integration="klar_nlu")),
        vol.Optional(CONF_URL, default=defaults.get(CONF_URL, "")): str,
        vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Required(CONF_WEATHER, default=defaults.get(CONF_WEATHER, True)): bool,
    })


def validate(hass, data):
    url = data.get(CONF_URL, "")
    if (data.get(CONF_WEATHER, True) or url) and not valid_url(url):
        return {"base": "invalid_url"}
    try:
        validate_target(hass, data.get(CONF_AGENT))
    except (ValueError, KeyError):
        return {"base": "invalid_agent"}
    return {}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = validate(self.hass, user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="Klar Assist Extensions", data=user_input)
        return self.async_show_form(step_id="user", data_schema=schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = validate(self.hass, user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="", data=user_input)
        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=schema(defaults), errors=errors)
