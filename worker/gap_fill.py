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


# ── Historical universe reconstruction ────────────────────────────────

def build_historical_universe(
    provider,
    gap_date: date,
    settings,
    rate_limiter: RateLimiter,
) -> List[ProbeUniverseItem]:
    """Build the instrument universe that was active on gap_date.

    Merges:
    1. Spot index (always available)
    2. Current instruments still active that were also active on gap_date
    3. Expired option contracts for expiries that overlapped gap_date
    Futures from the current catalog that were active on gap_date.

    DTE filtering is anchored to gap_date, not today.
    """
    from phase0.instruments import filter_nifty_derivatives
    from phase0.providers.upstox.history import (
        fetch_expired_option_contracts,
        fetch_expired_expiries,
        fetch_historical_candles,
    )

    max_dte = settings.max_dte_days
    spot_key = settings.spot_instrument_key

    # 1. Spot — always present
    universe: List[ProbeUniverseItem] = [
        ProbeUniverseItem(
            role="spot",
            exchange="NSE",
            tradingsymbol="Nifty 50",
            instrument_key=spot_key,
            provider="upstox",
        )
    ]

    # 2. Current instruments still active that were also active on gap_date
    all_current = provider.sync_instruments()
    nifty_current = filter_nifty_derivatives(
        all_current,
        symbol_name="NIFTY",
        derivative_segment=settings.derivative_segment,
    )

    current_keys_seen: set = set()

    # 2a. Futures from current catalog active on gap_date
    current_futures = sorted(
        [r for r in nifty_current
         if r.get("instrument_type") == "FUT"
         and _row_expiry(r) is not None
         and _row_expiry(r) >= gap_date],
        key=lambda r: _row_expiry(r),
    )
    for index, row in enumerate(current_futures):
        role = "future_front" if index == 0 else ("future_next" if index == 1 else "future_far")
        item = _row_to_universe_item(row, role)
        universe.append(item)
        if item.instrument_key:
            current_keys_seen.add(item.instrument_key)

    # 2b. Options from current catalog active on gap_date within DTE horizon
    current_options = [
        r for r in nifty_current
        if r.get("instrument_type") in {"CE", "PE"}
        and _row_expiry(r) is not None
        and _row_expiry(r) >= gap_date
        and (_row_expiry(r) - gap_date).days <= max_dte
    ]
    for row in current_options:
        item = _row_to_universe_item(row, "option")
        universe.append(item)
        if item.instrument_key:
            current_keys_seen.add(item.instrument_key)

    # 3. Expired contracts not in current catalog
    try:
        rate_limiter.wait_if_needed()
        all_expired_expiries = fetch_expired_expiries(provider.client, spot_key)
    except Exception as exc:
        log.warning("Failed to fetch expired expiries: %s", exc)
        all_expired_expiries = []

    # Filter to expiries active on gap_date and within DTE horizon
    relevant_expiries = [
        e for e in all_expired_expiries
        if date.fromisoformat(e) >= gap_date
        and (date.fromisoformat(e) - gap_date).days <= max_dte
    ]
    # Include one expiry beyond horizon for stable 90D interpolation
    beyond = [
        e for e in all_expired_expiries
        if date.fromisoformat(e) > gap_date + timedelta(days=max_dte)
    ]
    if beyond:
        relevant_expiries.append(beyond[0])

    for exp_str in relevant_expiries:
        rate_limiter.wait_if_needed()
        try:
            contracts = fetch_expired_option_contracts(provider.client, spot_key, exp_str)
        except Exception as exc:
            log.warning("Failed to fetch expired contracts for %s: %s", exp_str, exc)
            continue

        exp_date = date.fromisoformat(exp_str)
        for c in contracts:
            ikey = c.get("expired_instrument_key") or c.get("instrument_key") or ""
            if not ikey or ikey in current_keys_seen:
                continue
            current_keys_seen.add(ikey)
            universe.append(ProbeUniverseItem(
                role="option",
                exchange="NFO",
                tradingsymbol=c.get("tradingsymbol") or c.get("trading_symbol") or "",
                instrument_key=ikey,
                provider="upstox",
                segment="NSE_FO",
                instrument_type=c.get("instrument_type") or c.get("option_type"),
                expiry=exp_date,
                strike=float(c["strike_price"]) if c.get("strike_price") else None,
                option_type=c.get("option_type") or c.get("instrument_type"),
            ))

    # 4. Moneyness filter — get gap-date spot price
    try:
        rate_limiter.wait_if_needed()
        spot_candles = fetch_historical_candles(
            provider.client, spot_key, interval="day",
            from_date=gap_date, to_date=gap_date,
        )
        if spot_candles:
            gap_spot = spot_candles[0]["close"]
        else:
            gap_spot = None
    except Exception:
        gap_spot = None

    if gap_spot is not None:
        # Keep options within 80-120% moneyness of gap-date spot
        min_strike = gap_spot * 0.80
        max_strike = gap_spot * 1.20
        universe = [
            item for item in universe
            if item.role != "option" or item.strike is None
            or min_strike <= item.strike <= max_strike
        ]

    log.info("Built historical universe for %s: %d instruments (%d expired contracts fetched)",
             gap_date, len(universe), sum(1 for i in universe if i.instrument_key and i.instrument_key not in current_keys_seen))

    return universe


def _row_expiry(row: Dict) -> Optional[date]:
    """Extract expiry date from an instrument row."""
    value = row.get("expiry")
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _row_to_universe_item(row: Dict, role: str) -> ProbeUniverseItem:
    """Convert an instrument row dict to a ProbeUniverseItem."""
    expiry = _row_expiry(row)
    strike_val = row.get("strike") or row.get("strike_price")
    return ProbeUniverseItem(
        role=role,
        exchange="NFO",
        tradingsymbol=row.get("tradingsymbol") or row.get("trading_symbol") or "",
        instrument_key=row.get("instrument_key"),
        instrument_token=int(row["instrument_token"]) if row.get("instrument_token") else None,
        provider="upstox",
        segment=row.get("segment"),
        instrument_type=row.get("instrument_type"),
        expiry=expiry,
        strike=float(strike_val) if strike_val else None,
        option_type=row.get("option_type"),
        lot_size=int(row["lot_size"]) if row.get("lot_size") else None,
    )


# ── Backfill pipeline ────────────────────────────────────────────────

def backfill_day(
    gap: Gap,
    universe: Sequence[ProbeUniverseItem],
    client,  # UpstoxClient
    rate: float,
    rate_limiter: RateLimiter,
    db=None,  # WorkerDatabase
    baselines: Optional[Dict[str, List[float]]] = None,
    flow_baselines: Optional[Dict[str, List[float]]] = None,
    prior_close: Optional[Dict[str, Optional[float]]] = None,
) -> Dict:
    """Backfill one gap day using historical candles.

    For each instrument, fetches 1-minute candles and builds synthetic
    option snapshots. Then runs compute_expiry_nodes per minute.

    Returns summary dict.
    """
    day = gap.gap_date
    log.info("Backfilling %s (%s, ~%d minutes)", day, gap.gap_type, gap.missing_minutes)

    # Gap-fill log tracking
    log_id = None
    gap_start_ts = datetime.combine(day, MARKET_OPEN, tzinfo=IST)
    gap_end_ts = datetime.combine(day, MARKET_CLOSE, tzinfo=IST)
    if db is not None:
        try:
            log_id = db.insert_gap_fill_log(gap_start_ts, gap_end_ts, gap.gap_type, gap.missing_minutes)
            db.commit()
        except Exception as log_exc:
            log.warning("Failed to insert gap_fill_log: %s", log_exc)

    minutes_filled = 0
    try:
        result = _backfill_day_inner(
            gap, universe, client, rate, rate_limiter, db,
            baselines=baselines, flow_baselines=flow_baselines,
            prior_close=prior_close or {},
        )
        minutes_filled = result["minutes_filled"]

        if db is not None and log_id:
            minutes = market_minutes_for_day(day)
            status = "completed" if minutes_filled == len(minutes) else (
                "partial" if minutes_filled > 0 else "unfillable")
            db.update_gap_fill_log(log_id, status, minutes_filled)
            db.commit()

        return result

    except Exception as exc:
        if db is not None and log_id:
            try:
                db.update_gap_fill_log(log_id, "unfillable", minutes_filled, str(exc)[:500])
                db.commit()
            except Exception:
                pass
        raise


def _backfill_day_inner(
    gap: Gap,
    universe: Sequence[ProbeUniverseItem],
    client,
    rate: float,
    rate_limiter: RateLimiter,
    db=None,
    baselines: Optional[Dict[str, List[float]]] = None,
    flow_baselines: Optional[Dict[str, List[float]]] = None,
    prior_close: Optional[Dict[str, Optional[float]]] = None,
) -> Dict:
    """Inner backfill logic extracted for gap_fill_log wrapping."""
    from phase0.providers.upstox.history import (
        fetch_expired_historical_candles,
        fetch_historical_candles,
    )

    day = gap.gap_date

    # Collect all option instruments
    option_items = [item for item in universe if item.role == "option" and item.instrument_key]
    future_items = [item for item in universe if item.role.startswith("future") and item.instrument_key]
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
    from dataclasses import asdict
    from phase0.interpolation import interpolate_constant_maturity
    from phase0.metrics import (
        FLOW_BASE_METRICS,
        compute_flow_metrics,
        compute_level_metrics,
        compute_surface_grid,
        level_metrics_to_dict,
    )
    from worker.buffers import FlowRingBuffer
    from worker.percentile import (
        compute_abs_flow_percentiles,
        compute_level_percentiles,
        compute_state_score,
        compute_stress_score,
    )

    minutes = market_minutes_for_day(day)
    minutes_filled = 0
    flow_buffer = FlowRingBuffer()
    last_level_dict: Optional[Dict[str, Optional[float]]] = None
    last_flow_dict: Optional[Dict[str, Optional[float]]] = None

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
            # Pipeline: expiry_nodes → CM → metrics → surface → flow → scores
            cm_nodes = interpolate_constant_maturity(expiry_nodes)
            level_points = compute_level_metrics(cm_nodes, minute_ts)
            level_dict = level_metrics_to_dict(level_points)
            surface_cells = compute_surface_grid(cm_nodes, minute_ts)

            # Flow metrics
            flow_buffer.append(minute_ts, {k: level_dict.get(k) for k in FLOW_BASE_METRICS})
            lagged = flow_buffer.get_lagged(minute_ts)
            flow_points = compute_flow_metrics(
                current_levels={k: level_dict.get(k) for k in FLOW_BASE_METRICS},
                lagged_levels=lagged,
                prior_close=prior_close or {},
                ts=minute_ts,
            )
            flow_dict = {p.metric_key: p.value for p in flow_points}

            # Percentiles and scores (if baselines available)
            level_pcts: Dict[str, Optional[float]] = {}
            state_score: Optional[float] = None
            stress_score: Optional[float] = None

            if baselines:
                level_pcts = compute_level_percentiles(level_dict, baselines)
                state_score = compute_state_score(level_pcts)
            if flow_baselines:
                abs_flow_pcts = compute_abs_flow_percentiles(flow_dict, flow_baselines)
                stress_score = compute_stress_score(abs_flow_pcts)

            # Write to DB
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

            # Level + flow + score metric rows
            metric_rows = [
                {
                    "ts": p.ts, "metric_key": p.metric_key,
                    "tenor_code": p.tenor_code, "window_code": p.window_code,
                    "value": p.value,
                    "percentile": level_pcts.get(p.metric_key),
                    "provisional": True,
                }
                for p in level_points
            ] + [
                {
                    "ts": p.ts, "metric_key": p.metric_key,
                    "tenor_code": p.tenor_code, "window_code": p.window_code,
                    "value": p.value, "percentile": None, "provisional": True,
                }
                for p in flow_points
            ]
            if state_score is not None:
                metric_rows.append({
                    "ts": minute_ts, "metric_key": "state_score",
                    "tenor_code": None, "window_code": None,
                    "value": state_score, "percentile": None, "provisional": True,
                })
            if stress_score is not None:
                metric_rows.append({
                    "ts": minute_ts, "metric_key": "stress_score",
                    "tenor_code": None, "window_code": None,
                    "value": stress_score, "percentile": None, "provisional": True,
                })
            db.upsert_metric_series(metric_rows, source_mode="historical_backfill")

            surface_rows = [
                {
                    "tenor_code": c.tenor_code, "delta_bucket": c.delta_bucket,
                    "as_of": minute_ts, "iv": c.iv, "quality_score": c.quality_score,
                }
                for c in surface_cells
            ]
            db.upsert_surface_cells(surface_rows)

            last_level_dict = level_dict
            last_flow_dict = flow_dict

            if minutes_filled % 50 == 0:
                db.commit()

        minutes_filled += 1

    # Write end-of-day baselines for full-day backfills
    if db is not None and gap.gap_type == "full_day" and last_level_dict:
        baseline_rows = [
            {"metric_date": day, "metric_key": k, "close_value": v}
            for k, v in last_level_dict.items() if v is not None
        ]
        if baseline_rows:
            db.upsert_metric_baselines(baseline_rows)
            log.info("Wrote %d level baselines for backfilled %s", len(baseline_rows), day)

        # Flow baselines from last minute
        if last_flow_dict:
            flow_baseline_rows = []
            for fkey, fval in last_flow_dict.items():
                if fval is None or not fkey.startswith("d_"):
                    continue
                # Parse d_<metric_key>_<window_code>
                parts = fkey[2:].rsplit("_", 1)
                if len(parts) == 2:
                    flow_baseline_rows.append({
                        "metric_date": day,
                        "metric_key": parts[0],
                        "window_code": parts[1],
                        "change_value": fval,
                    })
            if flow_baseline_rows:
                db.upsert_flow_baselines(flow_baseline_rows)
                log.info("Wrote %d flow baselines for backfilled %s", len(flow_baseline_rows), day)

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
