"""Complete German Weather provider; preserve the tested German wording."""
from .matcher import is_candidate
from .time_parser import complete_time
from .formatter import format_weather, compact_day, WEEKDAYS

_MESSAGES = {
    "entity_unavailable": "Eine freigegebene Wetterentity ist für diese Anfrage nicht verfügbar.",
    "unsupported": "Diese Wettervorhersage wird noch nicht unterstützt.",
    "data_unavailable": "Die Wetterdaten sind gerade nicht verfügbar.",
    "range_unavailable": "Für diesen Zeitraum liegt noch keine Wettervorhersage vor.",
    "day_unavailable": "Für diesen Tag liegt noch keine Wettervorhersage vor.",
    "unsupported_day": "Dieser Vorhersagetag wird noch nicht unterstützt.",
    "recognition_unavailable": "Die Wetteranfrage kann gerade nicht sicher erkannt werden.",
    "current": "Aktuell",
    "range_gap": "{label}: keine Vorhersage verfügbar.",
}


class GermanWeather:
    code = "de"
    is_candidate = staticmethod(is_candidate)
    complete_time = staticmethod(complete_time)
    format_weather = staticmethod(format_weather)
    compact_day = staticmethod(compact_day)

    def day_label(self, offset, weekday, *, explicit_weekday=False, compact=False):
        if explicit_weekday:
            return f"Am {WEEKDAYS[weekday]}"
        if offset == 0:
            return "Heute"
        if offset == 1:
            return "Morgen"
        return WEEKDAYS[weekday] if compact else f"Am {WEEKDAYS[weekday]}"

    def message(self, key, *, label=""):
        return _MESSAGES[key].format(label=label)
