"""Weather extension; only this module owns weather-specific orchestration."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry
from ...klar_client import KlarError
from ...module_manager import ModuleResult
from .languages import LANGUAGES
from .forecast import daily_forecasts
from .data import local_date


class WeatherModule:
    name = "weather"

    def __init__(self, hass, client, *, clock=None, languages=None):
        self.hass, self.client = hass, client
        self.clock = clock or (lambda zone: datetime.now(zone))
        self.languages = LANGUAGES if languages is None else languages

    def can_handle(self, request):
        provider = self.languages.resolve(request.language)
        return provider is not None and provider.is_candidate(request.text)

    async def _allowed_state(self, entity_id, context):
        if not entity_id.startswith("weather."):
            return None
        if context.user_id is not None:
            user = await self.hass.auth.async_get_user(context.user_id)
            if user is None or not user.is_active or not user.permissions.check_entity(entity_id, POLICY_READ):
                return None
        if not async_should_expose(self.hass, "conversation", entity_id):
            return None
        return self.hass.states.get(entity_id)

    def _preferred_area(self, request):
        ids = [getattr(request, key, None) for key in ("device_id", "satellite_id")]
        if not any(ids):
            return None
        registry = device_registry.async_get(self.hass)
        for identifier in ids:
            device = registry.async_get(identifier) if identifier else None
            if device and device.area_id:
                return device.area_id
        return None

    async def handle(self, request):
        provider = self.languages.resolve(request.language)
        # Also defend direct callers that did not call can_handle first.
        if provider is None or not provider.is_candidate(request.text):
            return None
        try:
            query = await self.client.weather(request, self._preferred_area(request))
            state = await self._allowed_state(query.entity_id, request.context)
            if state is None:
                return ModuleResult(provider.message("entity_unavailable"), True)
            query = provider.complete_time(request.text, query)
            if query.error:
                return ModuleResult(query.error, True)
            if query.unsupported:
                return ModuleResult(provider.message("unsupported"), True)
            if state.state in {"unknown", "unavailable"}:
                return ModuleResult(provider.message("data_unavailable"), True)
            zone = ZoneInfo(self.hass.config.time_zone)
            # One clock snapshot per request: no changing dates during await/service calls.
            today = self.clock(zone).astimezone(zone).date()
            if query.current:
                return ModuleResult(provider.format_weather({**state.attributes, "condition": state.state},
                                    state.attributes, provider.message("current"), current=True, rain_only=query.rain_only))
            rows = await daily_forecasts(self.hass, query.entity_id, request.context)
            by_date = {}
            for row in rows:
                day = local_date(row.get("datetime"), zone)
                if day is not None:
                    by_date.setdefault(day, row)
            if query.count is not None:
                if not by_date:
                    return ModuleResult(provider.message("range_unavailable"))
                sentences = []
                for offset in range(query.count):
                    day = today + timedelta(days=offset)
                    label = provider.day_label(offset, day.weekday(), compact=True)
                    row = by_date.get(day)
                    sentences.append(provider.compact_day(row, state.attributes, label) if row else
                                     provider.message("range_gap", label=label))
                return ModuleResult(" ".join(sentences))
            offset = query.offset
            label = query.label
            if query.weekday is not None:
                offset = (query.weekday - today.weekday()) % 7 or 7
                label = provider.day_label(offset, query.weekday, explicit_weekday=True)
            if offset is None or not 0 <= offset <= 7:
                return ModuleResult(provider.message("unsupported_day"), True)
            target = today + timedelta(days=offset)
            label = label or provider.day_label(offset, target.weekday())
            row = by_date.get(target)
            if row is None:
                return ModuleResult(provider.message("day_unavailable"))
            return ModuleResult(provider.format_weather(row, state.attributes, label, rain_only=query.rain_only))
        except KlarError:
            return ModuleResult(provider.message("recognition_unavailable"), True)
        except (HomeAssistantError, TimeoutError, ValueError, KeyError):
            return ModuleResult(provider.message("data_unavailable"), True)
