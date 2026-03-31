from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from phase0.time_utils import indian_timezone
from worker.calendar import (
    MINUTES_PER_SESSION,
    is_trading_day,
    market_minutes_for_day,
    previous_trading_day,
    trading_days_between,
)
from worker.gap_fill import Gap, RateLimiter, _row_to_universe_item, detect_gaps

IST = indian_timezone()


class TestTradingCalendar(unittest.TestCase):
    def test_weekday_is_trading(self):
        # 2026-03-16 is Monday
        self.assertTrue(is_trading_day(date(2026, 3, 16)))

    def test_saturday_not_trading(self):
        self.assertFalse(is_trading_day(date(2026, 3, 21)))

    def test_sunday_not_trading(self):
        self.assertFalse(is_trading_day(date(2026, 3, 22)))

    def test_sunday_not_trading_via_is_trading_day(self):
        # 2026-03-22 is Sunday
        self.assertFalse(is_trading_day(date(2026, 3, 22)))

    def test_trading_days_between(self):
        # Mon to Fri: 5 trading days (no holidays in empty set)
        days = trading_days_between(date(2026, 3, 16), date(2026, 3, 20))
        self.assertEqual(len(days), 5)
        self.assertEqual(days[0], date(2026, 3, 16))

    def test_market_minutes_count(self):
        minutes = market_minutes_for_day(date(2026, 3, 16))
        self.assertEqual(len(minutes), MINUTES_PER_SESSION)
        # First minute: 09:15, last: 15:29
        self.assertEqual(minutes[0].hour, 9)
        self.assertEqual(minutes[0].minute, 15)
        self.assertEqual(minutes[-1].hour, 15)
        self.assertEqual(minutes[-1].minute, 29)

    def test_market_minutes_weekend_empty(self):
        # 2026-03-22 is Sunday — no market minutes
        minutes = market_minutes_for_day(date(2026, 3, 22))
        self.assertEqual(len(minutes), 0)

    def test_previous_trading_day_skips_weekend(self):
        # 2026-03-23 is Monday — previous trading day is Friday 2026-03-20
        prev = previous_trading_day(date(2026, 3, 23))
        self.assertEqual(prev, date(2026, 3, 20))

    def test_previous_trading_day_weekday(self):
        prev = previous_trading_day(date(2026, 3, 18))
        self.assertEqual(prev, date(2026, 3, 17))


class TestGapDetection(unittest.TestCase):
    def test_no_gaps_when_caught_up(self):
        now = datetime(2026, 3, 16, 10, 5, tzinfo=IST)
        last = datetime(2026, 3, 16, 10, 3, tzinfo=IST)
        gaps = detect_gaps(last, now, max_days_back=1)
        self.assertEqual(len(gaps), 0)

    def test_full_day_gap(self):
        # Last sealed was Friday, now is Monday
        last = datetime(2026, 3, 13, 15, 29, tzinfo=IST)  # Friday
        now = datetime(2026, 3, 16, 10, 0, tzinfo=IST)    # Monday
        gaps = detect_gaps(last, now, max_days_back=5)
        # Should detect Monday (today, intraday)
        day_types = {g.gap_date: g.gap_type for g in gaps}
        self.assertIn(date(2026, 3, 16), day_types)

    def test_none_last_sealed(self):
        now = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        gaps = detect_gaps(None, now, max_days_back=1)
        self.assertGreater(len(gaps), 0)

    def test_weekend_skipped(self):
        last = datetime(2026, 3, 13, 15, 29, tzinfo=IST)  # Friday
        now = datetime(2026, 3, 16, 9, 0, tzinfo=IST)     # Monday pre-market
        gaps = detect_gaps(last, now, max_days_back=5)
        # Saturday and Sunday should not appear
        gap_dates = {g.gap_date for g in gaps}
        self.assertNotIn(date(2026, 3, 14), gap_dates)
        self.assertNotIn(date(2026, 3, 15), gap_dates)


class TestRateLimiter(unittest.TestCase):
    def test_allows_initial_requests(self):
        rl = RateLimiter(per_sec=10, per_min=100, per_30min=500)
        # Should not block for first few requests
        for _ in range(5):
            rl.wait_if_needed()
        self.assertGreater(len(rl._timestamps), 0)

    def test_prunes_old_timestamps(self):
        rl = RateLimiter()
        # Manually add old timestamps
        import time as time_mod
        old_time = time_mod.monotonic() - 2000  # older than 30 min
        rl._timestamps.append(old_time)
        rl._prune(time_mod.monotonic())
        self.assertEqual(len(rl._timestamps), 0)


class TestRowToUniverseItem(unittest.TestCase):
    def test_option_type_from_instrument_type(self):
        """option_type should fall back to instrument_type when option_type key is absent."""
        row = {
            "instrument_key": "NSE_FO|NIFTY25APR22000CE",
            "tradingsymbol": "NIFTY25APR22000CE",
            "instrument_type": "CE",
            "segment": "NSE_FO",
            "expiry": date(2026, 4, 9),
            "strike": 22000.0,
            "lot_size": 25,
        }
        item = _row_to_universe_item(row, "option")
        self.assertEqual(item.option_type, "CE")

    def test_option_type_explicit_takes_precedence(self):
        """If row has an explicit option_type key, it should be used."""
        row = {
            "instrument_key": "NSE_FO|NIFTY25APR22000PE",
            "tradingsymbol": "NIFTY25APR22000PE",
            "instrument_type": "PE",
            "option_type": "PE",
            "segment": "NSE_FO",
            "expiry": date(2026, 4, 9),
            "strike": 22000.0,
        }
        item = _row_to_universe_item(row, "option")
        self.assertEqual(item.option_type, "PE")


if __name__ == "__main__":
    unittest.main()
