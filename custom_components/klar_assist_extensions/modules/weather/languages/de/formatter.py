"""German speech for already bound weather intents; no utterance parsing or LLM."""

from __future__ import annotations

from typing import Any
from ...data import number, local_date

CONDITIONS = {
    "clear-night": "klar", "cloudy": "bewölkt", "exceptional": "außergewöhnlich",
    "fog": "neblig", "hail": "hagelig", "lightning": "gewittrig",
    "lightning-rainy": "regnerisch mit Gewittern", "partlycloudy": "teilweise bewölkt",
    "pouring": "stark regnerisch", "rainy": "regnerisch", "snowy": "verschneit",
    "snowy-rainy": "regnerisch mit Schnee", "sunny": "sonnig", "windy": "windig",
    "windy-variant": "windig und bewölkt",
}
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def spoken_number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def bounded(value: Any, maximum: float | None = None) -> float | None:
    result = number(value)
    return result if result is not None and result >= 0 and (maximum is None or result <= maximum) else None


def wind_kmh(value: Any, unit: Any) -> float | None:
    speed = bounded(value)
    factor = {"km/h": 1, "m/s": 3.6, "mph": 1.609344, "mi/h": 1.609344,
              "kn": 1.852, "ft/s": 1.09728}.get(str(unit))
    return number(speed * factor) if speed is not None and factor is not None else None


def cloud_description(value: Any) -> str | None:
    coverage = bounded(value, 100)
    if coverage is None:
        return None
    for upper, description in ((10, "klar"), (30, "leicht bewölkt"), (60, "teilweise bewölkt"),
                               (85, "stark bewölkt"), (100, "bedeckt")):
        if coverage <= upper:
            return description
    return None


def wind_description(speed: float) -> str:
    for upper, description in ((2, "windstill"), (12, "leichter Wind"), (20, "schwacher Wind"),
                               (29, "mäßiger Wind"), (39, "frischer Wind"), (50, "starker Wind"),
                               (62, "stürmischer Wind")):
        if speed < upper:
            return description
    return "Sturm" if speed <= 74 else "schwerer Sturm"


def wind_sentence(values: dict[str, Any], units: dict[str, Any]) -> str | None:
    speed = wind_kmh(values.get("wind_speed"), units.get("wind_speed_unit"))
    if speed is None:
        return None
    # The final category starts strictly above 74 km/h, including fractional values.
    category = wind_description(speed)
    if category == "windstill":
        return "Es ist windstill."
    if speed < 39:
        return f"Es weht ein {category}."
    intro = f"Es weht ein {category}" if category.endswith("Wind") else f"Es herrscht {category}"
    sentence = f"{intro} mit Windgeschwindigkeiten um {spoken_number(speed)} Kilometer pro Stunde."
    gust = wind_kmh(values.get("wind_gust_speed"), units.get("wind_speed_unit"))
    if gust is not None and gust >= speed * 1.3 and gust - speed >= 10:
        sentence += f" Böen erreichen etwa {spoken_number(gust)} Kilometer pro Stunde."
    return sentence


def temperature(value: Any, units: dict[str, Any]) -> float | None:
    temp = number(value)
    unit = units.get("temperature_unit")
    if temp is None or unit not in {"°C", "°F"}:
        return None
    return number((temp - 32) * 5 / 9) if unit == "°F" else temp


def precipitation(value: Any, units: dict[str, Any]) -> float | None:
    amount = bounded(value)
    unit = units.get("precipitation_unit")
    if amount is None or unit not in {"mm", "in"}:
        return None
    return number(amount * 25.4) if unit == "in" else amount


def rain_sentences(values: dict[str, Any], units: dict[str, Any], label: str | None = None) -> list[str]:
    result = []
    probability = bounded(values.get("precipitation_probability"), 100)
    amount = precipitation(values.get("precipitation"), units)
    if probability is not None:
        lead = f"{label} beträgt die" if label else "Die"
        verb = "" if label else " beträgt"
        result.append(f"{lead} Regenwahrscheinlichkeit{verb} {spoken_number(probability)} Prozent.")
    if amount is not None:
        # Niederschlag can also mean snow/hail; do not claim that all of it is rain.
        result.append(f"Erwartet werden etwa {spoken_number(amount)} Millimeter Niederschlag.")
    return result


def format_weather(values: dict[str, Any], units: dict[str, Any], label: str,
                   *, current: bool = False, rain_only: bool = False) -> str:
    rain = rain_sentences(values, units, label if rain_only else None)
    if rain_only:
        return " ".join(rain) or f"Für {label.lower()} liegen keine Niederschlagswerte vor."
    sentences = []
    condition = CONDITIONS.get(str(values.get("condition", "")))
    if condition:
        sentences.append(f"Aktuell ist es {condition}." if current else f"{label} wird es {condition}.")
    high = temperature(values.get("temperature"), units)
    low = None if current else temperature(values.get("templow"), units)
    if low is not None and high is not None and low <= high:
        sentences.append(f"Die Temperaturen liegen zwischen {spoken_number(low)} und {spoken_number(high)} Grad.")
    else:
        if low is not None:
            sentences.append(f"Die Tiefsttemperatur liegt bei {spoken_number(low)} Grad.")
        if high is not None:
            sentences.append(f"Die Temperatur liegt bei {spoken_number(high)} Grad." if current else
                             f"Die Höchsttemperatur liegt bei {spoken_number(high)} Grad.")
    sentences.extend(rain)
    humidity = bounded(values.get("humidity"), 100)
    if humidity is not None:
        sentences.append(f"Die Luftfeuchtigkeit liegt bei {spoken_number(humidity)} Prozent.")
    clouds = cloud_description(values.get("cloud_coverage"))
    if clouds:
        sentences.append(f"Es ist {clouds}.")
    wind = wind_sentence(values, units)
    if wind:
        sentences.append(wind)
    return " ".join(sentences) or "Es liegen gerade keine Wetterwerte vor."


def compact_day(values: dict[str, Any], units: dict[str, Any], label: str) -> str:
    parts = []
    condition = CONDITIONS.get(str(values.get("condition", "")))
    if condition:
        parts.append(condition)
    low, high = temperature(values.get("templow"), units), temperature(values.get("temperature"), units)
    if low is not None and high is not None and low <= high:
        parts.append(f"{spoken_number(low)} bis {spoken_number(high)} Grad")
    else:
        if low is not None:
            parts.append(f"mindestens {spoken_number(low)} Grad")
        if high is not None:
            parts.append(f"höchstens {spoken_number(high)} Grad")
    amount = precipitation(values.get("precipitation"), units)
    if amount is not None and amount >= 5:
        parts.append(f"etwa {spoken_number(amount)} Millimeter Niederschlag")
    wind = wind_kmh(values.get("wind_speed"), units.get("wind_speed_unit"))
    if wind is not None and wind >= 50:
        parts.append(wind_description(wind))
    return f"{label} {', '.join(parts)}." if parts else f"{label}: keine Wetterwerte verfügbar."
