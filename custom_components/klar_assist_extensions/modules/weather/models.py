"""Weather vocabulary independent of Klar's JSON/slots."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherQuery:
    entity_id: str
    rain_only: bool = False
    current: bool = True
    offset: int | None = None
    weekday: int | None = None
    count: int | None = None
    # Explicit native date/part information must never be overwritten.
    native_time: bool = False
    unsupported: bool = False
    label: str | None = None
    error: str | None = None
