"""Daily HA forecast boundary; retain the original user's Context."""
import asyncio
from typing import Any
from .data import number

FIELDS = ("temperature", "templow", "precipitation", "precipitation_probability",
          "humidity", "cloud_coverage", "wind_speed", "wind_gust_speed")


async def daily_forecasts(hass: Any, entity_id: str, context: Any) -> list[dict[str, Any]]:
    async with asyncio.timeout(15):
        response = await hass.services.async_call(
            "weather", "get_forecasts", {"type": "daily", "entity_id": entity_id},
            blocking=True, return_response=True, context=context)
    payload = response.get(entity_id) if isinstance(response, dict) else None
    rows = payload.get("forecast") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [{"datetime": str(row.get("datetime") or "")[:64],
             "condition": str(row.get("condition") or "")[:64],
             **{field: number(row.get(field)) for field in FIELDS}}
            for row in rows[:8] if isinstance(row, dict)]
