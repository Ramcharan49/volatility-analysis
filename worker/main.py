"""V1 continuous worker: phase-aware lifecycle for NIFTY vol pipeline.

Entry point: python -m worker.main
"""
from __future__ import annotations

import logging
import signal
import sys
import time as time_mod
from dataclasses import asdict
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional

from phase0.config import Settings, load_settings
from phase0.interpolation import interpolate_constant_maturity
from phase0.live import MinuteAccumulator, SealedMinuteResult, ensure_ist
from phase0.metrics import (
    FLOW_BASE_METRICS,
    FLOW_METRIC_KEYS,
    LEVEL_METRIC_KEYS,
    compute_flow_metrics,
    compute_level_metrics,
    compute_surface_grid,
    level_metrics_to_dict,
)
from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone
from worker.daily_brief import generate_daily_brief, generate_dashboard_payload
from worker.db import WorkerDatabase
from worker.percentile import (
    compute_flow_percentiles,
    compute_level_percentiles,
    compute_state_score,
    compute_stress_score,
)

IST = indian_timezone()
WORKER_ID = "v1_nifty_worker"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("worker")


# ── Phase detection ──────────────────────────────────────────────────

PHASES = ("startup", "pre_market", "market_hours", "post_market", "idle")


def infer_phase(now: datetime, settings: Settings) -> str:
    """Determine current market phase from IST time."""
    now_ist = ensure_ist(now)
    t = now_ist.time()
    weekday = now_ist.weekday()

    if weekday >= 5:  # Saturday/Sunday
        return "idle"

    if t < settings.market_open:
        return "pre_market"
    if t <= settings.market_close:
        return "market_hours"
    if t <= time(16, 0):  # post-market window
        return "post_market"
    return "idle"


# ── Ring buffer for flow metric lookback ─────────────────────────────

class FlowRingBuffer:
    """In-memory ring buffer for recent level metric values.

    Stores up to max_minutes of historical level snapshots for
    computing flow metrics (5m, 15m, 60m deltas). Canonical source
    is the DB; this is an accelerator only.
    """

    def __init__(self, max_minutes: int = 65):
        self.max_minutes = max_minutes
        self._buffer: List[Dict] = []  # [{ts, metrics: {key: val}}]

    def append(self, ts: datetime, metrics: Dict[str, Optional[float]]) -> None:
        self._buffer.append({"ts": ts, "metrics": dict(metrics)})
        cutoff = ts - timedelta(minutes=self.max_minutes)
        self._buffer = [e for e in self._buffer if e["ts"] >= cutoff]

    def get_lagged(self, current_ts: datetime) -> Dict[str, Dict[str, Optional[float]]]:
        """Return lagged values for each flow window."""
        windows = {"5m": 5, "15m": 15, "60m": 60}
        result: Dict[str, Dict[str, Optional[float]]] = {}
        for window_code, minutes in windows.items():
            target_ts = current_ts - timedelta(minutes=minutes)
            closest = self._find_closest(target_ts)
            if closest is not None:
                result[window_code] = closest["metrics"]
        return result

    def _find_closest(self, target_ts: datetime) -> Optional[Dict]:
        if not self._buffer:
            return None
        best = None
        best_delta = None
        for entry in self._buffer:
            delta = abs((entry["ts"] - target_ts).total_seconds())
            if delta <= 90 and (best_delta is None or delta < best_delta):
                best = entry
                best_delta = delta
        return best

    def seed_from_db(self, db: WorkerDatabase, ref_ts: datetime) -> None:
        """Seed ring buffer from DB on startup/restart."""
        keys = list(FLOW_BASE_METRICS)
        data = db.fetch_latest_metric_values(keys, self.max_minutes, ref_ts)
        # Reconstruct per-minute entries
        by_ts: Dict[datetime, Dict] = {}
        for key, rows in data.items():
            for row in rows:
                ts = row["ts"]
                entry = by_ts.setdefault(ts, {})
                entry[key] = float(row["value"]) if row["value"] is not None else None
        for ts in sorted(by_ts.keys()):
            self.append(ts, by_ts[ts])
        if self._buffer:
            log.info("Seeded flow ring buffer with %d entries", len(self._buffer))


# ── Pipeline: process one sealed minute ──────────────────────────────

def process_sealed_minute(
    sealed: SealedMinuteResult,
    flow_buffer: FlowRingBuffer,
    prior_close: Dict[str, Optional[float]],
    db: Optional[WorkerDatabase] = None,
    source_mode: str = "live",
    baselines: Optional[Dict[str, List[float]]] = None,
    flow_baselines: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """Run the full derived-data pipeline for one sealed minute.

    Returns a summary dict with counts for logging.
    """
    ts = sealed.minute_ts

    # 1. Expiry nodes → ExpiryNode objects
    expiry_nodes = [
        ExpiryNode(**{k: v for k, v in row.items() if k in ExpiryNode.__dataclass_fields__})
        for row in sealed.expiry_node_rows
    ]

    # 2. Constant-maturity interpolation
    cm_nodes = interpolate_constant_maturity(expiry_nodes)

    # 3. Level metrics
    level_points = compute_level_metrics(cm_nodes, ts)
    level_dict = level_metrics_to_dict(level_points)

    # 4. Flow metrics
    flow_buffer.append(ts, {k: level_dict.get(k) for k in FLOW_BASE_METRICS})
    lagged = flow_buffer.get_lagged(ts)
    flow_points = compute_flow_metrics(
        current_levels={k: level_dict.get(k) for k in FLOW_BASE_METRICS},
        lagged_levels=lagged,
        prior_close=prior_close,
        ts=ts,
    )
    flow_dict = {p.metric_key: p.value for p in flow_points}

    # 5. Percentiles (if baselines available)
    level_pcts: Dict[str, Optional[float]] = {}
    flow_pcts: Dict[str, Optional[float]] = {}
    state_score: Optional[float] = None
    stress_score: Optional[float] = None

    if baselines is not None:
        level_pcts = compute_level_percentiles(level_dict, baselines)
    if flow_baselines is not None:
        flow_pcts = compute_flow_percentiles(flow_dict, flow_baselines)
    if level_pcts:
        state_score = compute_state_score(level_pcts)
    if flow_pcts:
        stress_score = compute_stress_score(flow_pcts)

    # 6. Surface grid
    surface_cells = compute_surface_grid(cm_nodes, ts)

    # 7. Write to DB
    if db is not None:
        # Expiry nodes
        db.upsert_expiry_nodes(sealed.expiry_node_rows, source_mode=source_mode)

        # CM nodes
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
        db.upsert_cm_nodes(cm_rows, source_mode=source_mode)

        # Metric series (level + flow) with percentiles
        metric_rows = [
            {
                "ts": p.ts, "metric_key": p.metric_key,
                "tenor_code": p.tenor_code, "window_code": p.window_code,
                "value": p.value,
                "percentile": level_pcts.get(p.metric_key),
                "provisional": baselines is None or len(baselines.get(p.metric_key, [])) < 60,
            }
            for p in level_points
        ] + [
            {
                "ts": p.ts, "metric_key": p.metric_key,
                "tenor_code": p.tenor_code, "window_code": p.window_code,
                "value": p.value,
                "percentile": flow_pcts.get(p.metric_key),
                "provisional": flow_baselines is None or len(flow_baselines.get(p.metric_key, [])) < 60,
            }
            for p in flow_points
        ]
        db.upsert_metric_series(metric_rows, source_mode=source_mode)

        # Surface cells
        surface_rows = [
            {
                "tenor_code": c.tenor_code, "delta_bucket": c.delta_bucket,
                "as_of": ts, "iv": c.iv, "quality_score": c.quality_score,
            }
            for c in surface_cells
        ]
        db.upsert_surface_cells(surface_rows)

        # Dashboard singleton update
        dashboard_payload = generate_dashboard_payload(
            ts, state_score, stress_score,
            level_dict, level_pcts, flow_dict,
        )
        db.upsert_dashboard(dashboard_payload)

        db.commit()

    return {
        "ts": ts.isoformat(),
        "expiry_nodes": len(expiry_nodes),
        "cm_nodes": len(cm_nodes),
        "level_metrics": len(level_points),
        "flow_metrics": len(flow_points),
        "surface_cells": len(surface_cells),
        "state_score": state_score,
        "stress_score": stress_score,
    }


# ── Worker lifecycle ─────────────────────────────────────────────────

class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.flow_buffer = FlowRingBuffer()
        self.prior_close: Dict[str, Optional[float]] = {}
        self.last_minute_sealed: Optional[datetime] = None
        self._stop = False

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        log.info("Worker starting (id=%s)", WORKER_ID)

        while not self._stop:
            now = datetime.now(IST)
            phase = infer_phase(now, self.settings)
            log.info("Current phase: %s", phase)

            if phase == "pre_market":
                self._run_pre_market()
            elif phase == "market_hours":
                self._run_market_hours()
            elif phase == "post_market":
                self._run_post_market()
            elif phase == "idle":
                log.info("Market idle. Sleeping 60s.")
                self._sleep(60)
            else:
                self._sleep(10)

    def _run_pre_market(self) -> None:
        log.info("Pre-market phase: waiting for market open at %s", self.settings.market_open)
        self._update_heartbeat("pre_market")

        # Run gap-fill for past-day gaps during pre-market
        if self.settings.supabase_db_url:
            self._run_gap_fill()

        while not self._stop:
            now = datetime.now(IST)
            if now.time() >= self.settings.market_open and now.weekday() < 5:
                break
            self._sleep(10)

    def _run_market_hours(self) -> None:
        log.info("Market hours: starting live pipeline")
        self._update_heartbeat("market_hours")

        # Import provider components
        from phase0.instruments import build_full_universe, filter_nifty_derivatives
        from phase0.providers import get_provider

        provider = get_provider(self.settings)
        session = provider.ensure_session(self.settings)
        if session is None:
            log.error("No session found. Run auth first: python phase0_probe.py auth --code <CODE>")
            self._update_heartbeat("error", error_message="No session")
            self._sleep(60)
            return

        # Build universe using provider (fixes C1, C2, H6)
        try:
            all_instruments = provider.sync_instruments()
            nifty = filter_nifty_derivatives(
                all_instruments,
                symbol_name=self.settings.phase0_symbol,
                derivative_segment=self.settings.derivative_segment,
            )
            spot_ltp_map = provider.get_ltp([self.settings.spot_instrument_key])
            spot_ltp = spot_ltp_map.get(self.settings.spot_instrument_key)
            if spot_ltp is None:
                log.error("Could not get spot LTP for %s", self.settings.spot_instrument_key)
                self._update_heartbeat("error", error_message="No spot LTP")
                self._sleep(60)
                return
            universe = build_full_universe(
                nifty, spot_ltp,
                max_dte_days=self.settings.max_dte_days,
                ws_token_limit=self.settings.ws_token_limit,
            )
            log.info("Universe: %d instruments", len(universe))
        except Exception as exc:
            log.error("Failed to build universe: %s", exc)
            if "401" in str(exc) or "Unauthorized" in str(exc):
                log.error("Auth expired. Re-authenticate: python phase0_probe.py auth --code <CODE>")
                self._update_heartbeat("error", error_message="Auth expired (401)")
            else:
                self._update_heartbeat("error", error_message=str(exc)[:200])
            self._sleep(60)
            return

        # Single DB connection for entire market session (fixes M1)
        db: Optional[WorkerDatabase] = None
        if self.settings.supabase_db_url:
            db = WorkerDatabase(self.settings.supabase_db_url)
            db.__enter__()

        try:
            if db is not None:
                # Seed flow buffer from DB
                try:
                    self.flow_buffer.seed_from_db(db, datetime.now(IST))
                except Exception as exc:
                    log.warning("Failed to seed flow buffer from DB: %s", exc)

                # Gap-fill: detect and fill gaps before going live (fixes H1)
                self._run_gap_fill_with_db(db, universe, provider)

                # Load prior_close from DB (fixes H2)
                self._load_prior_close(db)

                # Load baselines for percentile computation
                baselines = db.fetch_metric_baselines(lookback_days=252)
                flow_baselines_data = db.fetch_flow_baselines(lookback_days=252)
            else:
                baselines = None
                flow_baselines_data = None

            # Start accumulator + WebSocket
            accumulator = MinuteAccumulator(
                universe, self.settings.risk_free_rate,
                allow_ltp_fallback=self.settings.allow_ltp_fallback,
            )

            def on_ticks(ws, ticks):
                accumulator.feed_ticks(ticks, datetime.now(IST))

            def on_connect(ws, response):
                log.info("WebSocket connected")
                keys = [item.instrument_key for item in universe if item.instrument_key]
                ws.subscribe(keys)

            def on_error(ws, code, reason):
                log.warning("WebSocket error [%s]: %s", code, reason)
                if "401" in str(reason):
                    log.error("Auth expired during WebSocket. Re-authenticate.")

            ws = provider.create_websocket(
                access_token=session.access_token,
                on_ticks=on_ticks,
                on_connect=on_connect,
                on_error=on_error,
            )
            ws.connect(threaded=True)

            # Main loop: seal minutes and process
            try:
                while not self._stop:
                    now = datetime.now(IST)
                    if now.time() > self.settings.market_close:
                        break

                    sealed_list = accumulator.seal_ready(now, self.settings.seal_lag_seconds)
                    for sealed in sealed_list:
                        try:
                            summary = process_sealed_minute(
                                sealed, self.flow_buffer, self.prior_close,
                                db=db, source_mode="live",
                                baselines=baselines,
                                flow_baselines=flow_baselines_data,
                            )
                            self.last_minute_sealed = sealed.minute_ts
                            log.info(
                                "Sealed %s: %d expiry nodes, %d CM, %d metrics (state=%.1f, stress=%.1f)",
                                summary["ts"], summary["expiry_nodes"],
                                summary["cm_nodes"],
                                summary["level_metrics"] + summary["flow_metrics"],
                                summary["state_score"] or 0,
                                summary["stress_score"] or 0,
                            )
                            self._update_heartbeat("market_hours", db=db)
                        except Exception as exc:
                            log.error("Error processing sealed minute: %s", exc, exc_info=True)

                    self._sleep(1)
            finally:
                ws.close()

        except Exception as exc:
            log.error("Market hours error: %s", exc, exc_info=True)
        finally:
            if db is not None:
                db.__exit__(None, None, None)

    def _run_post_market(self) -> None:
        """Post-market: write baselines, compute closing percentiles, generate daily brief."""
        log.info("Post-market phase: writing baselines and daily brief")
        self._update_heartbeat("post_market")

        if not self.settings.supabase_db_url:
            self._sleep(60)
            return

        try:
            with WorkerDatabase(self.settings.supabase_db_url) as db:
                today = datetime.now(IST).date()

                # 1. Fetch today's last metric values from DB
                last_metrics = db.fetch_last_minute_metrics(today)
                if not last_metrics:
                    log.warning("No metric data found for today (%s), skipping post-market", today)
                    self._sleep(60)
                    return

                level_dict = {k: last_metrics[k] for k in LEVEL_METRIC_KEYS if k in last_metrics}
                flow_dict = {k: last_metrics[k] for k in FLOW_METRIC_KEYS if k in last_metrics}

                # 2. Write metric baselines (today's closing levels)
                baseline_rows = [
                    {"metric_date": today, "metric_key": k, "close_value": v}
                    for k, v in level_dict.items() if v is not None
                ]
                if baseline_rows:
                    db.upsert_metric_baselines(baseline_rows)
                    log.info("Wrote %d metric baselines for %s", len(baseline_rows), today)

                # 3. Write flow baselines (today's closing flow values)
                flow_baseline_rows = []
                for flow_key, value in flow_dict.items():
                    if value is None:
                        continue
                    # Parse flow key: d_{base}_{window}
                    parts = flow_key.split("_")
                    if len(parts) >= 3 and parts[0] == "d":
                        window_code = parts[-1]
                        base_key = "_".join(parts[1:-1])
                        flow_baseline_rows.append({
                            "metric_date": today,
                            "metric_key": base_key,
                            "window_code": window_code,
                            "change_value": value,
                        })
                if flow_baseline_rows:
                    db.upsert_flow_baselines(flow_baseline_rows)
                    log.info("Wrote %d flow baselines for %s", len(flow_baseline_rows), today)

                # 4. Compute closing percentiles
                baselines = db.fetch_metric_baselines(lookback_days=252)
                flow_baselines_data = db.fetch_flow_baselines(lookback_days=252)

                level_pcts = compute_level_percentiles(level_dict, baselines)
                flow_pcts = compute_flow_percentiles(flow_dict, flow_baselines_data)
                state_score = compute_state_score(level_pcts)
                stress_score = compute_stress_score(flow_pcts)

                log.info("Closing scores: state=%.1f, stress=%.1f",
                         state_score or 0, stress_score or 0)

                # 5. Update dashboard with closing snapshot
                dashboard_payload = generate_dashboard_payload(
                    datetime.now(IST), state_score, stress_score,
                    level_dict, level_pcts, flow_dict,
                )
                db.upsert_dashboard(dashboard_payload)

                # 6. Generate and write daily brief
                brief = generate_daily_brief(
                    today, state_score, stress_score,
                    level_dict, level_pcts, flow_dict,
                )
                db.upsert_daily_brief(brief)
                log.info("Daily brief written for %s: %s", today, brief.get("headline", ""))

                self._update_heartbeat("post_market", db=db)

        except Exception as exc:
            log.error("Post-market error: %s", exc, exc_info=True)
            self._update_heartbeat("error", error_message="Post-market: %s" % str(exc)[:200])

        # Sleep until idle phase
        self._sleep(60)

    def _run_gap_fill(self) -> None:
        """Run gap detection and backfill with its own DB connection."""
        try:
            with WorkerDatabase(self.settings.supabase_db_url) as db:
                from phase0.instruments import build_full_universe, filter_nifty_derivatives
                from phase0.providers import get_provider

                provider = get_provider(self.settings)
                session = provider.ensure_session(self.settings)
                if session is None:
                    log.warning("No session for gap-fill, skipping")
                    return

                all_instruments = provider.sync_instruments()
                nifty = filter_nifty_derivatives(
                    all_instruments,
                    symbol_name=self.settings.phase0_symbol,
                    derivative_segment=self.settings.derivative_segment,
                )
                spot_ltp_map = provider.get_ltp([self.settings.spot_instrument_key])
                spot_ltp = spot_ltp_map.get(self.settings.spot_instrument_key)
                if spot_ltp is None:
                    log.warning("No spot LTP for gap-fill, skipping")
                    return

                universe = build_full_universe(
                    nifty, spot_ltp,
                    max_dte_days=self.settings.max_dte_days,
                    ws_token_limit=self.settings.ws_token_limit,
                )
                self._run_gap_fill_with_db(db, universe, provider)
        except Exception as exc:
            log.warning("Gap-fill failed: %s", exc, exc_info=True)

    def _run_gap_fill_with_db(self, db: WorkerDatabase, universe, provider) -> None:
        """Detect and fill gaps using an existing DB connection."""
        from worker.gap_fill import RateLimiter, backfill_day, detect_gaps

        last_sealed = db.fetch_last_sealed_ts()
        gaps = detect_gaps(last_sealed, datetime.now(IST), self.settings.backfill_days)

        if not gaps:
            log.info("No gaps detected")
            return

        log.info("Detected %d gap(s) to fill", len(gaps))
        rate_limiter = RateLimiter()
        for gap in gaps:
            if self._stop:
                break
            result = backfill_day(
                gap, universe, provider.client,
                self.settings.risk_free_rate, rate_limiter, db,
            )
            log.info("Gap-fill result: %s", result)

    def _load_prior_close(self, db: WorkerDatabase) -> None:
        """Load prior-day closing values for 1D flow metrics (fixes H2)."""
        from worker.calendar import previous_trading_day

        prev_day = previous_trading_day(datetime.now(IST).date())
        prev_metrics = db.fetch_last_minute_metrics(prev_day)

        for key in FLOW_BASE_METRICS:
            if key in prev_metrics:
                self.prior_close[key] = prev_metrics[key]

        if self.prior_close:
            log.info("Loaded prior_close for %d metrics from %s", len(self.prior_close), prev_day)
        else:
            log.warning("No prior_close data found for %s — 1D flow metrics will be None", prev_day)

    def _update_heartbeat(self, phase: str, db: Optional[WorkerDatabase] = None,
                          error_message: Optional[str] = None) -> None:
        if self.settings.supabase_db_url is None:
            return
        try:
            if db is not None:
                db.upsert_heartbeat(
                    WORKER_ID, phase, datetime.now(IST),
                    self.last_minute_sealed, error_message=error_message,
                )
                db.commit()
            else:
                with WorkerDatabase(self.settings.supabase_db_url) as db_ctx:
                    db_ctx.upsert_heartbeat(
                        WORKER_ID, phase, datetime.now(IST),
                        self.last_minute_sealed, error_message=error_message,
                    )
        except Exception as exc:
            log.warning("Heartbeat update failed: %s", exc)

    def _handle_signal(self, signum, frame):
        log.info("Received signal %s, stopping", signum)
        self._stop = True

    def _sleep(self, seconds: float) -> None:
        end = time_mod.monotonic() + seconds
        while not self._stop and time_mod.monotonic() < end:
            time_mod.sleep(min(1.0, end - time_mod.monotonic()))


def main():
    settings = load_settings()
    worker = Worker(settings)
    worker.run()


if __name__ == "__main__":
    main()
