"""NSE trading calendar: holidays, market hours, trading day enumeration."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List, Set

from phase0.time_utils import indian_timezone

IST = indian_timezone()

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
MINUTES_PER_SESSION = 375  # 09:15 to 15:29 inclusive


# NSE holidays — left empty intentionally. If history mode or gap-fill
# hits a holiday, the API simply returns no candle data and it's handled
# gracefully. Populate from official NSE circulars if you want to skip
# unnecessary API calls on holidays.
NSE_HOLIDAYS: Set[date] = set()


def is_trading_day(d: date) -> bool:
    """Check if a date is a trading day (weekday and not a holiday)."""
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    return d not in NSE_HOLIDAYS


def trading_days_between(start: date, end: date) -> List[date]:
    """Return all trading days in [start, end] inclusive."""
    days = []
    current = start
    while current <= end:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def market_minutes_for_day(d: date) -> List[datetime]:
    """Return all minute timestamps for a trading day (09:15 to 15:29)."""
    if not is_trading_day(d):
        return []
    base = datetime.combine(d, MARKET_OPEN, tzinfo=IST)
    return [base + timedelta(minutes=i) for i in range(MINUTES_PER_SESSION)]


def previous_trading_day(d: date) -> date:
    """Return the most recent trading day before d."""
    current = d - timedelta(days=1)
    while not is_trading_day(current):
        current -= timedelta(days=1)
    return current
