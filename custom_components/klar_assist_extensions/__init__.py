"""Independent, modular Assist extensions. Does not import or patch Klar."""
from dataclasses import dataclass
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import CONF_AGENT, CONF_URL, CONF_TOKEN, CONF_WEATHER
from .klar_client import KlarClient
from .module_manager import ModuleManager
from .modules.weather.module import WeatherModule

PLATFORMS = [Platform.CONVERSATION]


@dataclass
class RuntimeData:
    manager: ModuleManager
    target_agent: str


async def async_setup_entry(hass, entry):
    from .conversation import validate_target
    from .klar_client import valid_url
    config = {**entry.data, **entry.options}
    if not isinstance(config.get(CONF_AGENT), str):
        raise ConfigEntryError("Missing Klar conversation target")
    try:
        validate_target(hass, config[CONF_AGENT])
    except (ValueError, KeyError) as err:
        raise ConfigEntryNotReady("Configured Klar conversation target is not available") from err
    modules = []
    if config.get(CONF_WEATHER, True):
        if not valid_url(config.get(CONF_URL, "")):
            raise ConfigEntryError("Invalid Klar API origin")
        client = KlarClient(async_get_clientsession(hass), config[CONF_URL], config.get(CONF_TOKEN, ""))
        modules.append(WeatherModule(hass, client))
    entry.runtime_data = RuntimeData(ModuleManager(modules), config[CONF_AGENT])
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        entry.runtime_data = None
        raise
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
    return unloaded
