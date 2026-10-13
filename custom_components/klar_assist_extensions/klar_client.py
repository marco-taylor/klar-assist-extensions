"""Only boundary to the public Klar v2 parse API; never execute/refine/render."""
import asyncio
from typing import Any
from urllib.parse import urlsplit
import aiohttp
from .modules.weather.models import WeatherQuery
from .language import normalize_language

_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class KlarError(Exception):
    """Transport error or incompatible/non-weather parse contract."""


def valid_url(url: str) -> bool:
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        # Access validates malformed/out-of-range ports as well.
        _ = parsed.port
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def decode_weather(payload: Any) -> WeatherQuery:
    """Never allow mixed/multiple steps, duplicate slots or unbound entities."""
    if not isinstance(payload, dict) or payload.get("schema_version") != "2.0":
        raise KlarError("Unsupported parse schema")
    if payload.get("decision") != {"type": "execute"}:
        raise KlarError("No executable weather request")
    plan = payload.get("plan")
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list) or len(steps) != 1:
        raise KlarError("Not a single weather step")
    item = steps[0].get("intent") if isinstance(steps[0], dict) else None
    if not isinstance(item, dict) or item.get("name") != "HassGetState":
        raise KlarError("Not a weather state query")
    slots = item.get("slots")
    if not isinstance(slots, list) or len(slots) > 32:
        raise KlarError("Invalid weather slots")
    values = {}
    for slot in slots:
        if (not isinstance(slot, dict) or not isinstance(slot.get("name"), str)
                or not isinstance(slot.get("value"), str) or slot["name"] in values
                or len(slot["value"]) > 512):
            raise KlarError("Invalid/duplicate weather slot")
        values[slot["name"]] = slot["value"]
    entity = values.get("entity_id", "")
    import re
    if not re.fullmatch(r"weather\.[a-z0-9_]+", entity) or values.get("domain") != "weather":
        raise KlarError("No bound weather entity")
    ask, day, part = (values.get(key, "") for key in ("weather_ask", "weather_day", "weather_part"))
    if ask not in {"now", "today", "tomorrow", "rain", "umbrella"}:
        raise KlarError("Unknown weather query")
    unsupported = bool(part) or ask == "umbrella" or day not in {"", "today", "tomorrow", *_DAYS}
    offset = 0 if day == "today" else 1 if day == "tomorrow" else None
    if not day:
        offset = 0 if ask == "today" else 1 if ask == "tomorrow" else None
    return WeatherQuery(entity_id=entity, rain_only=ask == "rain",
                        current=offset is None and day not in _DAYS,
                        offset=offset, weekday=_DAYS.get(day),
                        native_time=bool(day or part) or ask == "tomorrow",
                        unsupported=unsupported)


class KlarClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str = "", timeout: float = 10):
        if not valid_url(url):
            raise ValueError("Invalid Klar URL")
        self.session, self.url, self.token, self.timeout = session, url.rstrip('/'), token, timeout

    async def weather(self, request: Any, preferred_area: str | None = None) -> WeatherQuery:
        language = normalize_language(request.language)
        if language is None:
            raise KlarError("Invalid language code")
        body = {"text": request.text, "conversation_id": request.conversation_id,
                "language": language.language, "nlu_rag": False}
        if not request.conversation_id or len(request.conversation_id) > 128:
            raise KlarError("Missing/oversized conversation id")
        if preferred_area:
            body["preferred_area"] = preferred_area
        headers = {"X-Klar-Token": self.token} if self.token else {}
        try:
            async with self.session.post(self.url + "/api/v2/parse", json=body,
                                         headers=headers, allow_redirects=False,
                                         timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                if response.status != 200:
                    raise KlarError("Klar parse unavailable")
                if response.content_length is not None and response.content_length > 131072:
                    raise KlarError("Oversized parse response")
                raw = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    raw.extend(chunk)
                    if len(raw) > 131072:
                        raise KlarError("Oversized parse response")
                import json
                return decode_weather(json.loads(raw))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise KlarError("Klar parse unavailable or incompatible") from err
