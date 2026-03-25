from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def indian_timezone():
    for key in ("Asia/Kolkata", "Asia/Calcutta"):
        try:
            return ZoneInfo(key)
        except ZoneInfoNotFoundError:
            continue
    return timezone(timedelta(hours=5, minutes=30))
