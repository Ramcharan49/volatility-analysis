"""One-shot verification of the full V1 NIFTY vol pipeline with CSV export.

Two modes:
  snapshot  — single-point from REST quotes (~30s, works anytime)
  history   — full-day reconstruction from 1-min historical candles (~5-15 min)

Usage:
  python verify_pipeline.py snapshot --skip-db
  python verify_pipeline.py history --date 2026-03-28 --skip-db
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from phase0.artifacts import ensure_dir, write_csv
from phase0.config import load_settings
from phase0.interpolation import interpolate_constant_maturity
from phase0.metrics import (
    FLOW_BASE_METRICS,
    FLOW_METRIC_KEYS,
    LEVEL_METRIC_KEYS,
    compute_flow_metrics,
    compute_level_metrics,
    compute_surface_grid,
    level_metrics_to_dict,
)
from phase0.models import ProbeUniverseItem
from phase0.providers import get_provider
from phase0.quant import compute_expiry_nodes
from phase0.time_utils import indian_timezone
from worker.buffers import FlowRingBuffer
from worker.daily_brief import build_key_cards, build_insight_bullets
from worker.percentile import (
    classify_quadrant,
    compute_abs_flow_percentiles,
    compute_flow_percentiles,
    compute_level_percentiles,
    compute_state_score,
    compute_stress_score,
)

IST = indian_timezone()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("verify")


# ── CSV writers ──────────────────────────────────────────────────────

def _write_expiry_nodes_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    flat = []
    for r in rows:
        flat.append({
            "ts": r.get("ts"),
            "expiry": r.get("expiry"),
            "dte_days": r.get("dte_days"),
            "forward": r.get("forward"),
            "atm_strike": r.get("atm_strike"),
            "atm_iv": r.get("atm_iv"),
            "iv_25c": r.get("iv_25c"),
            "iv_25p": r.get("iv_25p"),
            "iv_10c": r.get("iv_10c"),
            "iv_10p": r.get("iv_10p"),
            "rr25": r.get("rr25"),
            "bf25": r.get("bf25"),
            "source_count": r.get("source_count"),
            "quality_score": r.get("quality_score"),
        })
    write_csv(out_dir / "01_expiry_nodes.csv", flat)
    return len(flat)


def _write_cm_nodes_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    write_csv(out_dir / "02_cm_nodes.csv", rows)
    return len(rows)


def _write_level_metrics_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    write_csv(out_dir / "03_level_metrics.csv", rows)
    return len(rows)


def _write_flow_metrics_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    write_csv(out_dir / "04_flow_metrics.csv", rows)
    return len(rows)


def _write_surface_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    write_csv(out_dir / "05_surface_grid.csv", rows)
    return len(rows)


def _write_scores_csv(out_dir: Path, rows: List[Dict]) -> int:
    if not rows:
        return 0
    write_csv(out_dir / "06_scores.csv", rows)
    return len(rows)


def _write_dashboard_csv(out_dir: Path, data: Dict) -> None:
    rows = [{"field": k, "value": v} for k, v in data.items()]
    write_csv(out_dir / "07_dashboard.csv", rows)


# ── Load baselines from DB (optional) ───────────────────────────────

def _load_baselines(settings):
    """Load baselines from DB if configured. Returns (baselines, flow_baselines) or (None, None)."""
    if not settings.supabase_db_url:
        return None, None
    try:
        from worker.db import WorkerDatabase
        with WorkerDatabase(settings.supabase_db_url) as db:
            baselines = db.fetch_metric_baselines(lookback_days=252)
            flow_baselines = db.fetch_flow_baselines(lookback_days=252)
            log.info("Loaded baselines: %d level keys, %d flow keys",
                     len(baselines), len(flow_baselines))
            return baselines, flow_baselines
    except Exception as exc:
        log.warning("Could not load baselines from DB: %s", exc)
        return None, None


# ── Pipeline: process one minute of data ─────────────────────────────

def _run_pipeline_for_minute(
    ts: datetime,
    expiry_nodes,
    flow_buffer: FlowRingBuffer,
    prior_close: Dict[str, Optional[float]],
    baselines,
    flow_baselines,
):
    """Run the full derived-data pipeline for one minute.

    Returns dict with all computed artifacts.
    """
    # CM interpolation
    cm_nodes = interpolate_constant_maturity(expiry_nodes)

    # Level metrics
    level_points = compute_level_metrics(cm_nodes, ts)
    level_dict = level_metrics_to_dict(level_points)

    # Flow metrics
    flow_buffer.append(ts, {k: level_dict.get(k) for k in FLOW_BASE_METRICS})
    lagged = flow_buffer.get_lagged(ts)
    flow_points = compute_flow_metrics(
        current_levels={k: level_dict.get(k) for k in FLOW_BASE_METRICS},
        lagged_levels=lagged,
        prior_close=prior_close,
        ts=ts,
    )
    flow_dict = {p.metric_key: p.value for p in flow_points}

    # Surface grid
    surface_cells = compute_surface_grid(cm_nodes, ts)

    # Percentiles + scores (if baselines available)
    level_pcts: Dict[str, Optional[float]] = {}
    flow_pcts: Dict[str, Optional[float]] = {}
    abs_flow_pcts: Dict[str, Optional[float]] = {}
    state_score: Optional[float] = None
    stress_score: Optional[float] = None

    if baselines is not None:
        level_pcts = compute_level_percentiles(level_dict, baselines)
    if flow_baselines is not None:
        flow_pcts = compute_flow_percentiles(flow_dict, flow_baselines)
        abs_flow_pcts = compute_abs_flow_percentiles(flow_dict, flow_baselines)
    if level_pcts:
        state_score = compute_state_score(level_pcts)
    if abs_flow_pcts:
        stress_score = compute_stress_score(abs_flow_pcts)

    quadrant = classify_quadrant(state_score, stress_score)

    return {
        "ts": ts,
        "expiry_nodes": expiry_nodes,
        "cm_nodes": cm_nodes,
        "level_points": level_points,
        "level_dict": level_dict,
        "flow_points": flow_points,
        "flow_dict": flow_dict,
        "surface_cells": surface_cells,
        "level_pcts": level_pcts,
        "flow_pcts": flow_pcts,
        "state_score": state_score,
        "stress_score": stress_score,
        "quadrant": quadrant,
    }


# ── Snapshot mode ────────────────────────────────────────────────────

def run_snapshot(settings, args) -> int:
    """Single-point verification from REST quotes."""
    from phase0.instruments import build_full_universe, filter_nifty_derivatives
    from phase0.providers.upstox.quotes import normalise_snapshots

    provider = get_provider(settings)
    session = provider.ensure_session(settings)
    log.info("Authenticated as %s", session.user_name or session.user_id)

    # Sync instruments
    log.info("Syncing instruments...")
    all_instruments = provider.sync_instruments()
    nifty = filter_nifty_derivatives(
        all_instruments,
        symbol_name=settings.phase0_symbol,
        derivative_segment=settings.derivative_segment,
    )
    log.info("  %d NIFTY derivatives found", len(nifty))

    # Get spot LTP
    spot_ltp_map = provider.get_ltp([settings.spot_instrument_key])
    spot_ltp = spot_ltp_map.get(settings.spot_instrument_key)
    if spot_ltp is None:
        log.error("Could not get spot LTP for %s", settings.spot_instrument_key)
        return 1
    log.info("  Spot LTP: %.2f", spot_ltp)

    # Build universe
    universe = build_full_universe(
        nifty, spot_ltp,
        max_dte_days=settings.max_dte_days,
        ws_token_limit=settings.ws_token_limit,
    )
    log.info("  Universe: %d instruments", len(universe))

    # Fetch REST quotes
    log.info("Fetching quotes...")
    quote_keys = [item.instrument_key for item in universe if item.instrument_key]
    quote_map = provider.fetch_quotes(quote_keys, batch_size=500)
    log.info("  Received quotes for %d instruments", len(quote_map))

    # Normalise snapshots → option rows
    snapshot_ts = datetime.now(IST).replace(second=0, microsecond=0)
    underlying_rows, option_rows = normalise_snapshots(universe, quote_map, snapshot_ts)

    # Get future price for expiry node computation
    future_price = None
    for row in underlying_rows:
        if row.get("source_type") == "future":
            future_price = row.get("last_price")
            break

    # Compute expiry nodes
    log.info("Computing expiry nodes...")
    expiry_nodes = compute_expiry_nodes(
        option_rows=option_rows,
        snapshot_ts=snapshot_ts,
        future_price=future_price,
        spot_price=spot_ltp,
        rate=settings.risk_free_rate,
        allow_ltp_fallback=True,
    )
    log.info("  %d expiry nodes", len(expiry_nodes))

    # Load baselines (optional)
    baselines, flow_baselines = (None, None) if args.skip_db else _load_baselines(settings)

    # Run full pipeline
    log.info("Running V1 pipeline...")
    flow_buffer = FlowRingBuffer()
    result = _run_pipeline_for_minute(
        ts=snapshot_ts,
        expiry_nodes=expiry_nodes,
        flow_buffer=flow_buffer,
        prior_close={},
        baselines=baselines,
        flow_baselines=flow_baselines,
    )

    # Write CSVs
    now = datetime.now(IST)
    out_dir = settings.artifacts_dir / ("verify_snapshot_%s" % now.strftime("%Y%m%d_%H%M%S"))
    ensure_dir(out_dir)

    n1 = _write_expiry_nodes_csv(out_dir, [asdict(n) for n in expiry_nodes])
    n2 = _write_cm_nodes_csv(out_dir, [
        {
            "ts": n.ts, "tenor_code": n.tenor_code, "tenor_days": n.tenor_days,
            "atm_iv": n.atm_iv, "iv_25c": n.iv_25c, "iv_25p": n.iv_25p,
            "iv_10c": n.iv_10c, "iv_10p": n.iv_10p,
            "rr25": n.rr25, "bf25": n.bf25, "quality": n.quality,
        }
        for n in result["cm_nodes"]
    ])
    n3 = _write_level_metrics_csv(out_dir, [
        {
            "ts": p.ts, "metric_key": p.metric_key, "tenor_code": p.tenor_code,
            "value": p.value,
            "percentile": result["level_pcts"].get(p.metric_key),
        }
        for p in result["level_points"]
    ])
    n4 = _write_flow_metrics_csv(out_dir, [
        {
            "ts": p.ts, "metric_key": p.metric_key, "window_code": p.window_code,
            "value": p.value,
            "percentile": result["flow_pcts"].get(p.metric_key),
        }
        for p in result["flow_points"]
    ])
    n5 = _write_surface_csv(out_dir, [
        {
            "ts": snapshot_ts, "tenor_code": c.tenor_code,
            "delta_bucket": c.delta_bucket,
            "iv": c.iv, "quality_score": c.quality_score,
        }
        for c in result["surface_cells"]
    ])
    n6 = _write_scores_csv(out_dir, [{
        "ts": snapshot_ts,
        "state_score": result["state_score"],
        "stress_score": result["stress_score"],
        "quadrant": result["quadrant"],
    }])

    # Dashboard summary
    cards = build_key_cards(
        result["level_dict"], result["level_pcts"], result["flow_dict"])
    bullets = build_insight_bullets(
        result["level_dict"], result["flow_dict"], result["level_pcts"])
    _write_dashboard_csv(out_dir, {
        "as_of": snapshot_ts.isoformat(),
        "state_score": result["state_score"],
        "stress_score": result["stress_score"],
        "quadrant": result["quadrant"],
        "key_cards": "; ".join("%s=%s" % (c["label"], c["value"] or "N/A") for c in cards),
        "insights": "; ".join(bullets) if bullets else "N/A",
    })

    # Print summary
    print()
    print("=" * 60)
    print("  VERIFICATION SUMMARY (snapshot)")
    print("=" * 60)
    ld = result["level_dict"]
    for key in ["atm_iv_7d", "atm_iv_30d", "atm_iv_90d", "rr25_30d", "bf25_30d", "term_7d_30d"]:
        val = ld.get(key)
        pct = result["level_pcts"].get(key)
        pct_str = "P%.0f" % pct if pct is not None else "N/A"
        val_str = "%.4f (%.2f%%)" % (val, val * 100) if val is not None else "N/A"
        print("  %-22s %s  [%s]" % (key, val_str, pct_str))
    print()
    print("  State Score:  %s" % (_fmt_score(result["state_score"])))
    print("  Stress Score: %s" % (_fmt_score(result["stress_score"])))
    print("  Quadrant:     %s" % (result["quadrant"] or "N/A"))
    print()
    print("  CSVs written to: %s" % out_dir)
    print("    01_expiry_nodes.csv    (%d rows)" % n1)
    print("    02_cm_nodes.csv        (%d rows)" % n2)
    print("    03_level_metrics.csv   (%d rows)" % n3)
    print("    04_flow_metrics.csv    (%d rows)" % n4)
    print("    05_surface_grid.csv    (%d rows)" % n5)
    print("    06_scores.csv          (%d rows)" % n6)
    print("    07_dashboard.csv       (summary)")
    print("=" * 60)
    return 0


# ── History mode ─────────────────────────────────────────────────────

def run_history(settings, args) -> int:
    """Full-day reconstruction from historical 1-minute candles."""
    from phase0.providers.upstox.history import (
        fetch_expired_historical_candles,
        fetch_historical_candles,
    )
    from worker.calendar import is_trading_day, market_minutes_for_day
    from worker.gap_fill import (
        RateLimiter,
        _build_synthetic_option_rows,
        _find_candle_at,
        _pick_candle_price,
        build_historical_universe,
    )

    target_date = date.fromisoformat(args.date)
    if not is_trading_day(target_date):
        log.error("%s is not a trading day (weekend or NSE holiday)", target_date)
        return 1

    provider = get_provider(settings)
    session = provider.ensure_session(settings)
    log.info("Authenticated as %s", session.user_name or session.user_id)

    rate_limiter = RateLimiter()

    # Build historical universe for target date
    log.info("Building historical universe for %s...", target_date)
    universe = build_historical_universe(provider, target_date, settings, rate_limiter)
    log.info("  Universe: %d instruments", len(universe))

    # Categorise instruments
    option_items = [i for i in universe if i.role == "option" and i.instrument_key]
    future_items = [i for i in universe if i.role.startswith("future") and i.instrument_key]
    spot_items = [i for i in universe if i.role == "spot" and i.instrument_key]
    log.info("  Options: %d, Futures: %d, Spot: %d",
             len(option_items), len(future_items), len(spot_items))

    # Fetch 1-minute candles for all instruments
    log.info("Fetching 1-minute candles (rate-limited)...")
    candles_by_key: Dict[str, List[Dict]] = {}
    all_items = option_items + future_items + spot_items
    fetch_count = 0

    for item in all_items:
        rate_limiter.wait_if_needed()
        try:
            candles = fetch_historical_candles(
                provider.client, item.instrument_key,
                interval="1minute",
                from_date=target_date,
                to_date=target_date,
            )
            if candles:
                candles_by_key[item.instrument_key] = candles
            fetch_count += 1
        except Exception as exc:
            if "expired" in str(exc).lower() or "404" in str(exc):
                try:
                    rate_limiter.wait_if_needed()
                    candles = fetch_expired_historical_candles(
                        provider.client, item.instrument_key,
                        interval="1minute",
                        from_date=target_date,
                        to_date=target_date,
                    )
                    if candles:
                        candles_by_key[item.instrument_key] = candles
                    fetch_count += 1
                except Exception:
                    pass
            else:
                log.debug("Candle fetch failed for %s: %s", item.instrument_key, exc)

        if fetch_count > 0 and fetch_count % 50 == 0:
            log.info("  Fetched %d/%d instruments...", fetch_count, len(all_items))

    log.info("  Candle data available for %d instruments", len(candles_by_key))

    if not candles_by_key:
        log.error("No candle data fetched for %s — cannot verify", target_date)
        return 1

    # Load baselines (optional)
    baselines, flow_baselines = (None, None) if args.skip_db else _load_baselines(settings)

    # Load prior close for 1d flow metrics
    prior_close: Dict[str, Optional[float]] = {}
    if not args.skip_db and settings.supabase_db_url:
        try:
            from worker.calendar import previous_trading_day
            from worker.db import WorkerDatabase
            prev_day = previous_trading_day(target_date)
            with WorkerDatabase(settings.supabase_db_url) as db:
                prev_metrics = db.fetch_last_minute_metrics(prev_day)
                prior_close = {k: prev_metrics.get(k) for k in FLOW_BASE_METRICS}
                if any(v is not None for v in prior_close.values()):
                    log.info("  Loaded prior_close from %s", prev_day)
        except Exception as exc:
            log.warning("  Could not load prior_close: %s", exc)

    # Process all 375 trading minutes
    minutes = market_minutes_for_day(target_date)
    log.info("Processing %d trading minutes...", len(minutes))

    flow_buffer = FlowRingBuffer()

    # Accumulators for CSV rows
    all_expiry_rows: List[Dict] = []
    all_cm_rows: List[Dict] = []
    all_level_rows: List[Dict] = []
    all_flow_rows: List[Dict] = []
    all_surface_rows: List[Dict] = []
    all_score_rows: List[Dict] = []

    minutes_with_data = 0
    last_level_dict: Optional[Dict] = None

    for i, minute_ts in enumerate(minutes):
        # Build synthetic option rows from candle close prices
        option_rows = _build_synthetic_option_rows(minute_ts, option_items, candles_by_key)
        if not option_rows:
            continue

        future_price = _pick_candle_price(minute_ts, future_items, candles_by_key)
        spot_price = _pick_candle_price(minute_ts, spot_items, candles_by_key)

        # Compute expiry nodes from synthetic options
        expiry_nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=minute_ts,
            future_price=future_price,
            spot_price=spot_price,
            rate=settings.risk_free_rate,
            allow_ltp_fallback=True,
        )

        if not expiry_nodes:
            continue

        # Run full pipeline
        result = _run_pipeline_for_minute(
            ts=minute_ts,
            expiry_nodes=expiry_nodes,
            flow_buffer=flow_buffer,
            prior_close=prior_close,
            baselines=baselines,
            flow_baselines=flow_baselines,
        )
        minutes_with_data += 1
        last_level_dict = result["level_dict"]

        # Accumulate CSV rows
        for n in expiry_nodes:
            d = asdict(n)
            d["ts"] = minute_ts
            all_expiry_rows.append(d)

        for n in result["cm_nodes"]:
            all_cm_rows.append({
                "ts": minute_ts, "tenor_code": n.tenor_code, "tenor_days": n.tenor_days,
                "atm_iv": n.atm_iv, "iv_25c": n.iv_25c, "iv_25p": n.iv_25p,
                "iv_10c": n.iv_10c, "iv_10p": n.iv_10p,
                "rr25": n.rr25, "bf25": n.bf25, "quality": n.quality,
            })

        for p in result["level_points"]:
            all_level_rows.append({
                "ts": p.ts, "metric_key": p.metric_key, "tenor_code": p.tenor_code,
                "value": p.value,
                "percentile": result["level_pcts"].get(p.metric_key),
            })

        for p in result["flow_points"]:
            all_flow_rows.append({
                "ts": p.ts, "metric_key": p.metric_key, "window_code": p.window_code,
                "value": p.value,
                "percentile": result["flow_pcts"].get(p.metric_key),
            })

        for c in result["surface_cells"]:
            all_surface_rows.append({
                "ts": minute_ts, "tenor_code": c.tenor_code,
                "delta_bucket": c.delta_bucket,
                "iv": c.iv, "quality_score": c.quality_score,
            })

        all_score_rows.append({
            "ts": minute_ts,
            "state_score": result["state_score"],
            "stress_score": result["stress_score"],
            "quadrant": result["quadrant"],
        })

        # Progress logging
        if minutes_with_data == 1:
            log.info("  First minute processed: %s", minute_ts.strftime("%H:%M"))
        elif minutes_with_data % 60 == 0:
            log.info("  Processed %d minutes (at %s)...",
                     minutes_with_data, minute_ts.strftime("%H:%M"))

    log.info("  Done: %d/%d minutes had data", minutes_with_data, len(minutes))

    if minutes_with_data == 0:
        log.error("No minutes produced data — cannot write CSVs")
        return 1

    # Write CSVs
    out_dir = settings.artifacts_dir / ("verify_history_%s" % target_date.isoformat())
    ensure_dir(out_dir)

    n1 = _write_expiry_nodes_csv(out_dir, all_expiry_rows)
    n2 = _write_cm_nodes_csv(out_dir, all_cm_rows)
    n3 = _write_level_metrics_csv(out_dir, all_level_rows)
    n4 = _write_flow_metrics_csv(out_dir, all_flow_rows)
    n5 = _write_surface_csv(out_dir, all_surface_rows)
    n6 = _write_scores_csv(out_dir, all_score_rows)

    # Dashboard from last minute
    last_result = result  # from the last processed minute
    cards = build_key_cards(
        last_result["level_dict"], last_result["level_pcts"], last_result["flow_dict"])
    bullets = build_insight_bullets(
        last_result["level_dict"], last_result["flow_dict"], last_result["level_pcts"])
    _write_dashboard_csv(out_dir, {
        "date": target_date.isoformat(),
        "minutes_processed": minutes_with_data,
        "state_score": last_result["state_score"],
        "stress_score": last_result["stress_score"],
        "quadrant": last_result["quadrant"],
        "key_cards": "; ".join("%s=%s" % (c["label"], c["value"] or "N/A") for c in cards),
        "insights": "; ".join(bullets) if bullets else "N/A",
    })

    # Print summary
    ld = last_result["level_dict"]
    print()
    print("=" * 60)
    print("  VERIFICATION SUMMARY (history: %s)" % target_date)
    print("=" * 60)
    print("  Minutes processed: %d / %d" % (minutes_with_data, len(minutes)))
    print()
    print("  Closing values (last minute):")
    for key in ["atm_iv_7d", "atm_iv_30d", "atm_iv_90d", "rr25_30d", "bf25_30d", "term_7d_30d"]:
        val = ld.get(key)
        pct = last_result["level_pcts"].get(key)
        pct_str = "P%.0f" % pct if pct is not None else "N/A"
        val_str = "%.4f (%.2f%%)" % (val, val * 100) if val is not None else "N/A"
        print("  %-22s %s  [%s]" % (key, val_str, pct_str))

    # Show flow metric warm-up status
    fd = last_result["flow_dict"]
    flow_populated = sum(1 for v in fd.values() if v is not None)
    print()
    print("  Flow metrics: %d/20 populated at close" % flow_populated)
    print()
    print("  State Score:  %s" % _fmt_score(last_result["state_score"]))
    print("  Stress Score: %s" % _fmt_score(last_result["stress_score"]))
    print("  Quadrant:     %s" % (last_result["quadrant"] or "N/A"))
    print()
    print("  CSVs written to: %s" % out_dir)
    print("    01_expiry_nodes.csv    (%d rows)" % n1)
    print("    02_cm_nodes.csv        (%d rows)" % n2)
    print("    03_level_metrics.csv   (%d rows)" % n3)
    print("    04_flow_metrics.csv    (%d rows)" % n4)
    print("    05_surface_grid.csv    (%d rows)" % n5)
    print("    06_scores.csv          (%d rows)" % n6)
    print("    07_dashboard.csv       (summary)")
    print("=" * 60)
    return 0


# ── Helpers ──────────────────────────────────────────────────────────

def _fmt_score(score: Optional[float]) -> str:
    if score is None:
        return "N/A (no baselines)"
    return "%.1f" % score


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the full V1 NIFTY vol pipeline and export CSVs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Snapshot mode
    snap_parser = subparsers.add_parser(
        "snapshot", help="Single-point from REST quotes (works anytime)")
    snap_parser.add_argument("--skip-db", action="store_true",
                             help="Skip DB baselines (no percentiles/scores)")

    # History mode
    hist_parser = subparsers.add_parser(
        "history", help="Full-day from historical 1-min candles")
    hist_parser.add_argument("--date", required=True,
                             help="Target date in YYYY-MM-DD format")
    hist_parser.add_argument("--skip-db", action="store_true",
                             help="Skip DB baselines (no percentiles/scores)")

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "snapshot":
        return run_snapshot(settings, args)
    elif args.command == "history":
        return run_history(settings, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
