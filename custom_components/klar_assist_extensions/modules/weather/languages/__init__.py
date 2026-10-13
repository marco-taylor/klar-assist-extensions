"""Weather language interface and explicit providers; English is inactive."""
from typing import Any, Protocol
from ....language import LanguageRegistry
from ..models import WeatherQuery


class WeatherLanguage(Protocol):
    code: str
    def is_candidate(self, text: str) -> bool: ...
    def complete_time(self, text: str, query: WeatherQuery) -> WeatherQuery: ...
    def format_weather(self, values: dict[str, Any], units: dict[str, Any], label: str,
                       *, current: bool = False, rain_only: bool = False) -> str: ...
    def compact_day(self, values: dict[str, Any], units: dict[str, Any], label: str) -> str: ...
    def day_label(self, offset: int, weekday: int, *, explicit_weekday: bool = False,
                  compact: bool = False) -> str: ...
    def message(self, key: str, *, label: str = "") -> str: ...


from .de import GermanWeather
from .en import CODE as ENGLISH_CODE

LANGUAGES: LanguageRegistry[WeatherLanguage] = LanguageRegistry()
LANGUAGES.register("de", GermanWeather())
LANGUAGES.register(ENGLISH_CODE, None)
