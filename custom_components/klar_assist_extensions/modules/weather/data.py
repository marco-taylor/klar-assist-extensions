"""Language-neutral numeric validation and forecast date conversion."""
import math
from datetime import datetime, date
from typing import Any
from zoneinfo import ZoneInfo


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def local_date(stamp: Any, zone: ZoneInfo) -> date | None:
    if not isinstance(stamp, str):
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        return moment.astimezone(zone).date() if moment.tzinfo else None
    except (ValueError, OverflowError):
        return None
