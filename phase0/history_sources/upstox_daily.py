from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional

from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
from phase0.providers import get_provider
from phase0.time_utils import indian_timezone


IST = indian_timezone()


class UpstoxDailyHistorySource:
    name = "upstox"

    def __init__(self, settings, provider=None):
        self.settings = settings
        self.provider = provider or get_provider(settings)

    def build_close_snapshot(self, target_date: date) -> DailyBuildResult:
        from phase0.providers.upstox.history import (
            fetch_expired_historical_candles,
            fetch_historical_candles,
        )
        from worker.gap_fill import RateLimiter, build_historical_universe

        session = self.provider.ensure_session(self.settings)
        rate_limiter = RateLimiter()
        universe = build_historical_universe(self.provider, target_date, self.settings, rate_limiter)
        option_items = [i for i in universe if i.role == "option" and i.instrument_key]
        future_items = [i for i in universe if i.role.startswith("future") and i.instrument_key]
        spot_items = [i for i in universe if i.role == "spot" and i.instrument_key]

        all_items = option_items + future_items + spot_items
        candles_by_key: Dict[str, List[Dict]] = {}
        for item in all_items:
            rate_limiter.wait_if_needed()
            try:
                candles = fetch_historical_candles(
                    self.provider.client,
                    item.instrument_key,
                    interval="day",
                    from_date=target_date,
                    to_date=target_date,
                )
            except Exception as exc:
                if "expired" not in str(exc).lower() and "404" not in str(exc):
                    raise
                rate_limiter.wait_if_needed()
                candles = fetch_expired_historical_candles(
                    self.provider.client,
                    item.instrument_key,
                    interval="day",
                    from_date=target_date,
                    to_date=target_date,
                )
            if candles:
                candles_by_key[item.instrument_key] = candles

        option_rows = []
        for item in option_items:
            candles = candles_by_key.get(item.instrument_key, [])
            if not candles:
                continue
            candle = candles[0]
            option_rows.append({
                "expiry": item.expiry,
                "strike": item.strike,
                "option_type": item.option_type,
                "bid": None,
                "ask": None,
                "ltp": candle["close"],
                "volume": candle.get("volume", 0),
                "oi": candle.get("oi", 0),
                "quote_quality": "ltp_fallback",
            })

        future_price = None
        for item in future_items:
            candles = candles_by_key.get(item.instrument_key, [])
            if candles:
                future_price = candles[0]["close"]
                break

        spot_price = None
        for item in spot_items:
            candles = candles_by_key.get(item.instrument_key, [])
            if candles:
                spot_price = candles[0]["close"]
                break

        diagnostics = {
            "source_user": session.user_name or session.user_id,
            "option_row_count": len(option_rows),
            "future_row_count": len(future_items),
            "spot_row_count": len(spot_items),
        }
        if not option_rows:
            return DailyBuildResult(status="no_data", snapshot=None, diagnostics=diagnostics)

        snapshot = DailyCloseSnapshot(
            source_name=self.name,
            target_date=target_date,
            close_ts=datetime.combine(target_date, time(15, 29), tzinfo=IST),
            option_rows=option_rows,
            future_price=future_price,
            spot_price=spot_price,
            meta=diagnostics,
        )
        return DailyBuildResult(status="completed", snapshot=snapshot, diagnostics=diagnostics)
