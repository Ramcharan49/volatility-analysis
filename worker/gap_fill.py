"""Gap detection and historical backfill engine.

Detects missing trading minutes, fetches historical candles from Upstox,
builds synthetic snapshots, and runs the quant pipeline to fill gaps.
"""
from __future__ import annotations

import logging
import time as time_mod
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from phase0.models import ProbeUniverseItem
from phase0.quant import compute_expiry_nodes
from phase0.time_utils import indian_timezone
from worker.calendar import (
    MARKET_CLOSE,
    MARKET_OPEN,
    MINUTES_PER_SESSION,
    is_trading_day,
    market_minutes_for_day,
    trading_days_between,
)

IST = indian_timezone()
log = logging.getLogger("worker.gap_fill")


# ── Rate limiter ─────────────────────────────────────────────────────

class RateLimiter:
    """Sliding window rate limiter respecting Upstox free-tier limits.

    Limits:
    - 50 requests per second
    - 500 requests per minute
    - 2000 requests per 30 minutes (binding constraint)
    """

    def __init__(self, per_sec: int = 50, per_min: int = 500, per_30min: int = 2000):
        self.per_sec = per_sec
        self.per_min = per_min
        self.per_30min = per_30min
        self._timestamps: deque = deque()

    def wait_if_needed(self) -> None:
        """Block until it's safe to make another request."""
        now = time_mod.monotonic()
        self._prune(now)

        # Check 30-minute window (binding)
        if len(self._timestamps) >= self.per_30min:
            oldest = self._timestamps[0]
            wait = oldest + 1800 - now
            if wait > 0:
                log.debug("Rate limit: waiting %.1fs (30min window)", wait)
                time_mod.sleep(wait)
                now = time_mod.monotonic()
                self._prune(now)

        # Check 1-minute window
        one_min_ago = now - 60
        recent_min = sum(1 for t in self._timestamps if t > one_min_ago)
        if recent_min >= self.per_min:
            oldest_min = next(t for t in self._timestamps if t > one_min_ago)
            wait = oldest_min + 60 - now
            if wait > 0:
                log.debug("Rate limit: waiting %.1fs (1min window)", wait)
                time_mod.sleep(wait)
                now = time_mod.monotonic()

        # Check 1-second window
        one_sec_ago = now - 1
        recent_sec = sum(1 for t in self._timestamps if t > one_sec_ago)
        if recent_sec >= self.per_sec:
            time_mod.sleep(0.05)
            now = time_mod.monotonic()

        self._timestamps.append(now)

    def _prune(self, now: float) -> None:
        cutoff = now - 1800  # 30 minutes
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


# ── Gap detection ────────────────────────────────────────────────────

@dataclass
class Gap:
    gap_date: date
    gap_type: str  # 'full_day' or 'intraday'
    missing_minutes: int
    expected_minutes: int


def detect_gaps(
    last_sealed_ts: Optional[datetime],
    now: datetime,
    max_days_back: int = 1,
) -> List[Gap]:
    """Detect missing trading day gaps between last_sealed_ts and now."""
    now_ist = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    today = now_ist.date()

    if last_sealed_ts is None:
        start_date = today - timedelta(days=max_days_back)
    else:
        start_date = last_sealed_ts.astimezone(IST).date()

    trading_days = trading_days_between(start_date, today)
    gaps: List[Gap] = []

    for day in trading_days:
        if day == today:
            # Current day: check if we're behind
            if last_sealed_ts is not None:
                last_minute = last_sealed_ts.astimezone(IST).replace(second=0, microsecond=0)
                market_open_ts = datetime.combine(day, MARKET_OPEN, tzinfo=IST)
                if last_minute >= market_open_ts:
                    # Partially filled today
                    elapsed = int((now_ist - last_minute).total_seconds() / 60)
                    if elapsed > 2:  # More than 2 minutes behind
                        gaps.append(Gap(
                            gap_date=day,
                            gap_type="intraday",
                            missing_minutes=elapsed,
                            expected_minutes=MINUTES_PER_SESSION,
                        ))
                    continue

            # Full gap for today (if market has started)
            if now_ist.time() > MARKET_OPEN:
                gaps.append(Gap(
                    gap_date=day,
                    gap_type="intraday",
                    missing_minutes=min(
                        int((now_ist - datetime.combine(day, MARKET_OPEN, tzinfo=IST)).total_seconds() / 60),
                        MINUTES_PER_SESSION,
                    ),
                    expected_minutes=MINUTES_PER_SESSION,
                ))
        else:
            # Past day: check if sealed_ts covers it
            if last_sealed_ts is None or last_sealed_ts.astimezone(IST).date() < day:
                gaps.append(Gap(
                    gap_date=day,
                    gap_type="full_day",
                    missing_minutes=MINUTES_PER_SESSION,
                    expected_minutes=MINUTES_PER_SESSION,
                ))

    return gaps


# ── Backfill pipeline ────────────────────────────────────────────────

def backfill_day(
    gap: Gap,
    universe: Sequence[ProbeUniverseItem],
    client,  # UpstoxClient
    rate: float,
    rate_limiter: RateLimiter,
    db=None,  # WorkerDatabase
) -> Dict:
    """Backfill one gap day using historical candles.

    For each instrument, fetches 1-minute candles and builds synthetic
    option snapshots. Then runs compute_expiry_nodes per minute.

    Returns summary dict.
    """
    from phase0.providers.upstox.history import (
        fetch_expired_historical_candles,
        fetch_historical_candles,
    )

    day = gap.gap_date
    log.info("Backfilling %s (%s, ~%d minutes)", day, gap.gap_type, gap.missing_minutes)

    # Collect all option instruments
    option_items = [item for item in universe if item.role == "option" and item.instrument_key]
    future_items = [item for item in universe if item.role == "future_front" and item.instrument_key]
    spot_items = [item for item in universe if item.role == "spot" and item.instrument_key]

    # Fetch candles for each instrument
    candles_by_key: Dict[str, List[Dict]] = {}
    fetch_count = 0

    for item in option_items + future_items + spot_items:
        rate_limiter.wait_if_needed()
        try:
            candles = fetch_historical_candles(
                client, item.instrument_key,
                interval="1minute",
                from_date=day,
                to_date=day,
            )
            if candles:
                candles_by_key[item.instrument_key] = candles
            fetch_count += 1
        except Exception as exc:
            if "expired" in str(exc).lower() or "404" in str(exc):
                # Try expired endpoint
                try:
                    rate_limiter.wait_if_needed()
                    candles = fetch_expired_historical_candles(
                        client, item.instrument_key,
                        interval="1minute",
                        from_date=day,
                        to_date=day,
                    )
                    if candles:
                        candles_by_key[item.instrument_key] = candles
                    fetch_count += 1
                except Exception as inner_exc:
                    log.debug("Expired candle fetch failed for %s: %s", item.instrument_key, inner_exc)
            else:
                log.warning("Candle fetch failed for %s: %s", item.instrument_key, exc)

        if fetch_count % 100 == 0:
            log.info("Fetched candles for %d/%d instruments", fetch_count, len(option_items) + len(future_items) + len(spot_items))

    if not candles_by_key:
        log.warning("No candle data fetched for %s", day)
        return {"day": day.isoformat(), "minutes_filled": 0, "fetch_count": fetch_count}

    # Build per-minute synthetic snapshots and run pipeline
    minutes = market_minutes_for_day(day)
    minutes_filled = 0

    for minute_ts in minutes:
        option_rows = _build_synthetic_option_rows(
            minute_ts, option_items, candles_by_key,
        )
        if not option_rows:
            continue

        future_price = _pick_candle_price(minute_ts, future_items, candles_by_key)
        spot_price = _pick_candle_price(minute_ts, spot_items, candles_by_key)

        expiry_nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=minute_ts,
            future_price=future_price,
            spot_price=spot_price,
            rate=rate,
            allow_ltp_fallback=True,  # Always True for backfill
        )

        if expiry_nodes and db is not None:
            from dataclasses import asdict
            from phase0.interpolation import interpolate_constant_maturity
            from phase0.metrics import compute_level_metrics, compute_surface_grid

            # Pipeline: expiry_nodes → CM → metrics → surface
            cm_nodes = interpolate_constant_maturity(expiry_nodes)
            level_points = compute_level_metrics(cm_nodes, minute_ts)
            surface_cells = compute_surface_grid(cm_nodes, minute_ts)

            node_rows = [asdict(n) for n in expiry_nodes]
            db.upsert_expiry_nodes(node_rows, source_mode="historical_backfill")

            cm_rows = [
                {
                    "ts": n.ts, "tenor_code": n.tenor_code, "tenor_days": n.tenor_days,
                    "atm_iv": n.atm_iv, "iv_25c": n.iv_25c, "iv_25p": n.iv_25p,
                    "iv_10c": n.iv_10c, "iv_10p": n.iv_10p,
                    "rr25": n.rr25, "bf25": n.bf25,
                    "quality": n.quality,
                    "bracket_expiries": [e.isoformat() for e in n.bracket_expiries],
                }
                for n in cm_nodes
            ]
            db.upsert_cm_nodes(cm_rows, source_mode="historical_backfill")

            metric_rows = [
                {
                    "ts": p.ts, "metric_key": p.metric_key,
                    "tenor_code": p.tenor_code, "window_code": p.window_code,
                    "value": p.value, "percentile": None, "provisional": True,
                }
                for p in level_points
            ]
            db.upsert_metric_series(metric_rows, source_mode="historical_backfill")

            surface_rows = [
                {
                    "tenor_code": c.tenor_code, "delta_bucket": c.delta_bucket,
                    "as_of": minute_ts, "iv": c.iv, "quality_score": c.quality_score,
                }
                for c in surface_cells
            ]
            db.upsert_surface_cells(surface_rows)

            if minutes_filled % 50 == 0:
                db.commit()

        minutes_filled += 1

    if db is not None:
        db.commit()

    log.info("Backfilled %s: %d/%d minutes filled (%d instruments fetched)",
             day, minutes_filled, len(minutes), fetch_count)
    return {
        "day": day.isoformat(),
        "minutes_filled": minutes_filled,
        "fetch_count": fetch_count,
    }


def _build_synthetic_option_rows(
    minute_ts: datetime,
    option_items: Sequence[ProbeUniverseItem],
    candles_by_key: Dict[str, List[Dict]],
) -> List[Dict]:
    """Build synthetic option snapshot rows from candle close prices."""
    rows = []
    minute_str = minute_ts.strftime("%Y-%m-%dT%H:%M")

    for item in option_items:
        candles = candles_by_key.get(item.instrument_key, [])
        candle = _find_candle_at(candles, minute_str)
        if candle is None:
            continue

        rows.append({
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
    return rows


def _pick_candle_price(
    minute_ts: datetime,
    items: Sequence[ProbeUniverseItem],
    candles_by_key: Dict[str, List[Dict]],
) -> Optional[float]:
    """Get close price from candle data for underlying instruments."""
    minute_str = minute_ts.strftime("%Y-%m-%dT%H:%M")
    for item in items:
        candles = candles_by_key.get(item.instrument_key, [])
        candle = _find_candle_at(candles, minute_str)
        if candle is not None:
            return candle["close"]
    return None


def _find_candle_at(candles: List[Dict], minute_str: str) -> Optional[Dict]:
    """Find a candle matching the given minute timestamp."""
    for candle in candles:
        candle_date = candle.get("date", "")
        if isinstance(candle_date, str) and candle_date.startswith(minute_str):
            return candle
    return None
