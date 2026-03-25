"""NSE trading calendar: holidays, market hours, trading day enumeration."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List, Set

from phase0.time_utils import indian_timezone

IST = indian_timezone()

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
MINUTES_PER_SESSION = 375  # 09:15 to 15:29 inclusive


# NSE holidays for 2025 and 2026 (gazetted holidays when market is closed)
NSE_HOLIDAYS: Set[date] = {
    # 2025
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr (Ramadan)
    date(2025, 4, 10),   # Shri Mahavir Jayanti
    date(2025, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 6, 7),    # Bakri Id
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 16),   # Janmashtami
    date(2025, 10, 2),   # Mahatma Gandhi Jayanti
    date(2025, 10, 21),  # Diwali (Laxmi Pujan)
    date(2025, 10, 22),  # Diwali Balipratipada
    date(2025, 11, 5),   # Prakash Gurpurb Sri Guru Nanak Dev
    date(2025, 12, 25),  # Christmas
    # 2026
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 17),   # Mahashivratri
    date(2026, 3, 3),    # Holi
    date(2026, 3, 20),   # Id-Ul-Fitr
    date(2026, 3, 30),   # Shri Ram Navmi
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 25),   # Buddha Purnima
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 25),   # Milad-Un-Nabi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 9),   # Dussehra
    date(2026, 10, 29),  # Diwali (Laxmi Pujan)
    date(2026, 10, 30),  # Diwali Balipratipada
    date(2026, 11, 16),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


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
