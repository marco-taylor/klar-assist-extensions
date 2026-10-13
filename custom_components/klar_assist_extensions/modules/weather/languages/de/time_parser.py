"""Complete only missing dates of already verified weather requests."""
import re
from dataclasses import replace
from .matcher import normalize
from ...models import WeatherQuery

MAX_OFFSET = 7
MAX_DAYS = 8
NUMBERS = {"eins": 1, "ein": 1, "einen": 1, "einem": 1, "eine": 1,
           "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
           "sechs": 6, "sieben": 7, "acht": 8}
SPOKEN = {1: "einem", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben"}
_TIME = r"(?:übermorgen|uebermorgen|in \S+ tag(?:en)?|(?:für )?(?:die )?nächsten? \S+ tage|in den nächsten? \S+ tagen)"
_QUERY = re.compile(rf"(?:wetter (?P<bare>{_TIME})|wie wird (?:das wetter (?P<after>{_TIME})|(?P<before>{_TIME}) das wetter))")
_RANGE = re.compile(r"(?:(?:für )?(?:die )?nächsten? (\S+) tage|in den nächsten? (\S+) tagen)")
_UNRESOLVED_TIME = re.compile(
    r"\b(?:übermorgen|uebermorgen|morgen|gestern|nächsten?|naechsten?|"
    r"montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b|\bin \S+ tag(?:e|en)?\b")


def complete_time(text: str, query: WeatherQuery) -> WeatherQuery:
    if query.native_time or query.unsupported:
        return query
    normalized = normalize(text)
    match = _QUERY.fullmatch(normalized)
    if match is None or query.rain_only:
        # A broad candidate is not permission to silently substitute today's data.
        if _UNRESOLVED_TIME.search(normalized):
            return replace(query, error="Diese Zeitangabe wird noch nicht unterstützt.")
        return query
    temporal = next(value for value in match.groupdict().values() if value)
    if temporal in {"übermorgen", "uebermorgen"}:
        return replace(query, current=False, offset=2, label="Übermorgen")
    multiple = _RANGE.fullmatch(temporal)
    if multiple:
        token = next(value for value in multiple.groups() if value)
        maximum, kind = MAX_DAYS, "range"
    else:
        single = re.fullmatch(r"in (\S+) tag(?:en)?", temporal)
        if single is None:
            return query
        token, maximum, kind = single[1], MAX_OFFSET, "offset"
    count = int(token) if token.isascii() and token.isdigit() and len(token) <= 2 else NUMBERS.get(token)
    if count is None or not 1 <= count <= maximum:
        return replace(query, error=f"Bitte nenne eine Tageszahl zwischen 1 und {maximum}.")
    if kind == "range":
        return replace(query, current=False, count=count)
    label = "Übermorgen" if count == 2 else f"In {SPOKEN[count]} {'Tag' if count == 1 else 'Tagen'}"
    return replace(query, current=False, offset=count, label=label)
