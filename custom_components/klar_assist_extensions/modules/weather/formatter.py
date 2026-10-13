"""Compatibility exports for existing explicit German formatter callers."""
from .languages.de.formatter import (
    CONDITIONS, WEEKDAYS, number, spoken_number, bounded, wind_kmh, cloud_description,
    wind_description, wind_sentence, temperature, precipitation, rain_sentences,
    format_weather, local_date, compact_day,
)
