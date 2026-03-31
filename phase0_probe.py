from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from phase0.artifacts import append_jsonl, ensure_dir, read_jsonl, timestamp_slug, write_csv_artifact, write_json_artifact
from phase0.config import load_settings
from phase0.db import Phase0Database
from phase0.instruments import build_probe_universe, filter_nifty_derivatives, instrument_catalog_rows, phase0_universe_rows, pick_historical_targets
from phase0.live import MinuteAccumulator, compare_row_sets, ensure_ist, universe_items_from_rows
from phase0.providers import get_provider
from phase0.providers.upstox.quotes import normalise_snapshots
from phase0.quant import compute_expiry_nodes
from phase0.time_utils import indian_timezone


IST = indian_timezone()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 market data validation runner")
    parser.add_argument("--provider", default=None, help="Override data provider (default: from settings)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="Run interactive provider auth")
    auth_parser.add_argument("--no-browser", action="store_true", help="Print login URL instead of opening a browser")
    auth_parser.add_argument("--code", help="Authorization code from manual Upstox login (skip browser flow)")

    probe_parser = subparsers.add_parser("probe", help="Run the offline Phase 0 probe")
    probe_parser.add_argument("--skip-db", action="store_true", help="Skip all Supabase writes")
    probe_parser.add_argument("--skip-historical", action="store_true", help="Skip historical candle checks")
    probe_parser.add_argument("--allow-ltp-fallback", action="store_true", help="Allow LTP-only quote quality for off-market runs")
    probe_parser.add_argument("--quote-batch-size", type=int, default=500)
    probe_parser.add_argument("--strike-span", type=int, default=5)

    live_parser = subparsers.add_parser("live", help="Run the live websocket Phase 0 validation")
    live_parser.add_argument("--skip-db", action="store_true", help="Skip all Supabase writes")
    live_parser.add_argument("--allow-ltp-fallback", action="store_true", help="Allow LTP-only quote quality")
    live_parser.add_argument("--duration-minutes", type=int, default=30)
    live_parser.add_argument("--seal-lag-seconds", type=int, default=2)
    live_parser.add_argument("--strike-span", type=int, default=5)

    replay_parser = subparsers.add_parser("replay", help="Replay a saved live manifest deterministically")
    replay_parser.add_argument("--manifest", required=True, help="Path to a phase0 live manifest JSON file")
    replay_parser.add_argument("--skip-db", action="store_true", help="Skip all Supabase writes")
    replay_parser.add_argument("--allow-ltp-fallback", action="store_true", help="Allow LTP-only quote quality")

    subparsers.add_parser("history-probe", help="Validate expired instruments API for last N months")

    args = parser.parse_args()
    settings = load_settings()
    if args.provider:
        settings = settings._replace(provider=args.provider) if hasattr(settings, '_replace') else settings

    if args.command == "auth":
        provider = get_provider(settings)
        if args.code:
            session_state = provider.exchange_code(settings, args.code)
        else:
            session_state = provider.authenticate(settings, open_browser=not args.no_browser)
        print("Authenticated as %s" % session_state.user_id)
        print("Session saved to %s" % settings.session_state_path)
        return 0
    if args.command == "probe":
        return run_probe(settings, args)
    if args.command == "live":
        return run_live(settings, args)
    if args.command == "history-probe":
        return run_history_probe(settings, args)
    return run_replay(settings, args)


def run_probe(settings, args) -> int:
    ensure_dir(settings.artifacts_dir)
    provider = get_provider(settings)
    session = provider.ensure_session(settings)
    now = datetime.now(IST)
    stage = "instrument_sync"
    counts = _base_counts()
    artifact_paths: Dict[str, str] = {}
    report = None
    allow_ltp = getattr(args, "allow_ltp_fallback", False)

    db, db_context, run_id = _start_db_run(
        settings,
        skip_db=args.skip_db,
        probe_name="phase0_probe",
        mode="probe",
        user_id=session.user_id or "",
    )

    try:
        all_instruments = provider.sync_instruments()
        nifty_instruments = filter_nifty_derivatives(
            all_instruments,
            symbol_name=settings.phase0_symbol,
            derivative_segment=settings.derivative_segment,
        )
        as_of_date = now.date()
        instrument_rows = instrument_catalog_rows(nifty_instruments, as_of_date, provider=settings.provider)
        artifact_paths["instrument_catalog"] = _artifact_ref(
            write_csv_artifact(settings.artifacts_dir, "phase0_nifty_instruments", instrument_rows, now)
        )
        counts["nifty_instruments"] = len(nifty_instruments)
        if db:
            db.upsert_instrument_catalog(instrument_rows)

        stage = "quote_fetch"
        spot_ltp_map = provider.get_ltp([settings.spot_instrument_key])
        spot_ltp = spot_ltp_map.get(settings.spot_instrument_key)
        if spot_ltp is None:
            raise RuntimeError("Failed to fetch spot LTP for %s. Available keys: %s" % (
                settings.spot_instrument_key, list(spot_ltp_map.keys())))

        universe = build_probe_universe(
            nifty_instruments,
            spot_ltp=spot_ltp,
            strike_span=args.strike_span,
            spot_instrument_key=settings.spot_instrument_key,
            spot_exchange=settings.spot_exchange,
            spot_tradingsymbol=settings.spot_tradingsymbol,
            provider=settings.provider,
        )
        universe_rows = phase0_universe_rows(run_id, universe, as_of_date)
        artifact_paths["universe"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_universe", universe_rows, now)
        )
        counts["universe_items"] = len(universe_rows)
        if db:
            db.insert_phase0_universe(universe_rows)

        quote_keys = [item.instrument_key for item in universe if item.instrument_key]
        quote_map = provider.fetch_quotes(quote_keys, batch_size=args.quote_batch_size)
        counts["quote_payloads"] = len(quote_map)
        snapshot_ts = datetime.now(IST).replace(second=0, microsecond=0)
        underlying_rows, option_rows = normalise_snapshots(universe, quote_map, snapshot_ts)
        artifact_paths["underlying_snapshots"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_underlying_snapshots", underlying_rows, now)
        )
        artifact_paths["option_snapshots"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_option_snapshots", option_rows, now)
        )
        counts["underlying_snapshots"] = len(underlying_rows)
        counts["option_snapshots"] = len(option_rows)

        historical_samples: Dict[str, List[Dict]] = {}
        if not args.skip_historical:
            stage = "historical_fetch"
            for item in pick_historical_targets(universe, spot_ltp):
                if not item.instrument_key:
                    continue
                historical_samples[item.instrument_key] = provider.fetch_historical(
                    item.instrument_key,
                    interval="1minute",
                )
            artifact_paths["historical_samples"] = _artifact_ref(
                write_json_artifact(settings.artifacts_dir, "phase0_historical_samples", historical_samples, now)
            )
        counts["historical_series"] = len(historical_samples)

        stage = "quant_compute"
        future_price = _future_price_from_rows(universe, underlying_rows)
        expiry_nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=snapshot_ts,
            future_price=future_price,
            spot_price=spot_ltp,
            rate=settings.risk_free_rate,
            allow_ltp_fallback=allow_ltp,
            strike_step=settings.strike_step,
        )
        expiry_node_rows = [asdict(node) for node in expiry_nodes]
        artifact_paths["expiry_nodes"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_expiry_nodes", expiry_node_rows, now)
        )
        counts["expiry_nodes"] = len(expiry_nodes)

        if db:
            stage = "db_write"
            db.upsert_underlying_snapshots(underlying_rows)
            db.upsert_option_snapshots(option_rows)
            db.upsert_expiry_nodes(expiry_node_rows)

        report = {
            "run_id": run_id,
            "as_of": now,
            "symbol": settings.phase0_symbol,
            "provider": settings.provider,
            "mode": "probe",
            "user_id": session.user_id,
            "counts": counts,
            "sample_expiry_nodes": expiry_node_rows[:2],
            "stress_window": "1d",
            "artifact_paths": artifact_paths,
        }
        artifact_paths["report"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_validation_report", report, now)
        )
        artifact_paths["manifest"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_probe_manifest", _manifest_payload(settings, "probe", session.user_id, counts, artifact_paths, now), now)
        )
        print("Probe complete.")
        return 0
    except Exception as exc:
        _record_stage_failure(db, run_id, stage, exc, {"stress_window": "1d"})
        raise
    finally:
        _finish_db_run(db, db_context, run_id, report, stage, counts, artifact_paths, settings, "probe", session.user_id)


def run_live(settings, args) -> int:
    ensure_dir(settings.artifacts_dir)
    provider = get_provider(settings)
    session = provider.ensure_session(settings)
    now = datetime.now(IST)
    stage = "instrument_sync"
    counts = _base_counts()
    counts["ticks_received"] = 0
    counts["sealed_minutes"] = 0
    counts["reconnects"] = 0
    artifact_paths: Dict[str, str] = {}
    report = None
    allow_ltp = getattr(args, "allow_ltp_fallback", False)

    db, db_context, run_id = _start_db_run(
        settings,
        skip_db=args.skip_db,
        probe_name="phase0_live",
        mode="live",
        user_id=session.user_id or "",
    )

    try:
        all_instruments = provider.sync_instruments()
        nifty_instruments = filter_nifty_derivatives(
            all_instruments,
            symbol_name=settings.phase0_symbol,
            derivative_segment=settings.derivative_segment,
        )
        as_of_date = now.date()
        instrument_rows = instrument_catalog_rows(nifty_instruments, as_of_date, provider=settings.provider)
        artifact_paths["instrument_catalog"] = _artifact_ref(
            write_csv_artifact(settings.artifacts_dir, "phase0_live_nifty_instruments", instrument_rows, now)
        )
        counts["nifty_instruments"] = len(nifty_instruments)
        if db:
            db.upsert_instrument_catalog(instrument_rows)

        stage = "quote_fetch"
        spot_ltp_map = provider.get_ltp([settings.spot_instrument_key])
        spot_ltp = spot_ltp_map.get(settings.spot_instrument_key)
        if spot_ltp is None:
            raise RuntimeError("Failed to fetch spot LTP for %s. Available keys: %s" % (
                settings.spot_instrument_key, list(spot_ltp_map.keys())))

        universe = build_probe_universe(
            nifty_instruments,
            spot_ltp=spot_ltp,
            strike_span=args.strike_span,
            spot_instrument_key=settings.spot_instrument_key,
            spot_exchange=settings.spot_exchange,
            spot_tradingsymbol=settings.spot_tradingsymbol,
            provider=settings.provider,
        )
        universe_rows = phase0_universe_rows(run_id, universe, as_of_date)
        artifact_paths["universe"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_live_universe", universe_rows, now)
        )
        counts["universe_items"] = len(universe_rows)
        if db:
            db.insert_phase0_universe(universe_rows)

        run_slug = timestamp_slug(now)
        raw_ticks_path = settings.artifacts_dir / ("phase0_live_ticks_%s.jsonl" % run_slug)
        sealed_underlying_path = settings.artifacts_dir / ("phase0_live_underlying_%s.jsonl" % run_slug)
        sealed_options_path = settings.artifacts_dir / ("phase0_live_options_%s.jsonl" % run_slug)
        sealed_nodes_path = settings.artifacts_dir / ("phase0_live_expiry_nodes_%s.jsonl" % run_slug)
        artifact_paths["raw_ticks"] = _artifact_ref(raw_ticks_path)
        artifact_paths["sealed_underlying"] = _artifact_ref(sealed_underlying_path)
        artifact_paths["sealed_options"] = _artifact_ref(sealed_options_path)
        artifact_paths["sealed_expiry_nodes"] = _artifact_ref(sealed_nodes_path)

        accumulator = MinuteAccumulator(universe, settings.risk_free_rate, allow_ltp_fallback=allow_ltp, strike_step=settings.strike_step)
        lock = threading.Lock()
        connected = threading.Event()
        state: Dict[str, Optional[Exception]] = {"fatal": None}
        subscribed_keys = sorted(accumulator.items_by_key)

        def on_connect(ws, response):
            if not subscribed_keys:
                state["fatal"] = RuntimeError("No instrument keys available for websocket subscribe.")
                return
            try:
                ws.subscribe(subscribed_keys)
                connected.set()
            except Exception as exc:
                state["fatal"] = exc

        def on_ticks(ws, ticks):
            received_at = datetime.now(IST)
            with lock:
                accumulator.feed_ticks(ticks, received_at)
                counts["ticks_received"] += len(ticks)
                for tick in ticks:
                    append_jsonl(raw_ticks_path, {"received_at": received_at, "tick": tick})

        def on_reconnect(ws, attempts_count):
            counts["reconnects"] += 1
            if db:
                db.record_probe_event(
                    run_id,
                    "websocket_reconnect",
                    "WebSocket reconnect attempt %s" % attempts_count,
                    {"attempts_count": attempts_count},
                )
                db.commit()

        def on_error(ws, code, reason):
            if not connected.is_set() and state["fatal"] is None:
                state["fatal"] = RuntimeError("WebSocket connect failed: %s" % reason)

        stage = "websocket_connect"
        ws = provider.create_websocket(
            access_token=session.access_token,
            on_ticks=on_ticks,
            on_connect=on_connect,
            on_error=on_error,
            on_reconnect=on_reconnect,
        )
        ws.connect(threaded=True)

        if not connected.wait(timeout=30):
            raise RuntimeError("Timed out waiting for WebSocket connection.")

        end_at = datetime.now(IST) + timedelta(minutes=args.duration_minutes)
        while datetime.now(IST) < end_at:
            if state["fatal"] is not None:
                raise state["fatal"]
            time.sleep(1)
            sealed_results = _collect_ready_minutes(accumulator, lock, args.seal_lag_seconds)
            for result in sealed_results:
                counts["sealed_minutes"] += 1
                counts["underlying_snapshots"] += len(result.underlying_rows)
                counts["option_snapshots"] += len(result.option_rows)
                counts["expiry_nodes"] += len(result.expiry_node_rows)
                _persist_sealed_result(result, sealed_underlying_path, sealed_options_path, sealed_nodes_path)
                if db:
                    stage = "db_write"
                    db.upsert_underlying_snapshots(result.underlying_rows)
                    db.upsert_option_snapshots(result.option_rows)
                    db.upsert_expiry_nodes(result.expiry_node_rows)
                    db.commit()

        ws.close()
        for result in _collect_ready_minutes(accumulator, lock, args.seal_lag_seconds):
            counts["sealed_minutes"] += 1
            counts["underlying_snapshots"] += len(result.underlying_rows)
            counts["option_snapshots"] += len(result.option_rows)
            counts["expiry_nodes"] += len(result.expiry_node_rows)
            _persist_sealed_result(result, sealed_underlying_path, sealed_options_path, sealed_nodes_path)
            if db:
                stage = "db_write"
                db.upsert_underlying_snapshots(result.underlying_rows)
                db.upsert_option_snapshots(result.option_rows)
                db.upsert_expiry_nodes(result.expiry_node_rows)
                db.commit()

        if counts["sealed_minutes"] <= 0:
            raise RuntimeError("No sealed minutes were produced during the live run.")

        report = {
            "run_id": run_id,
            "as_of": now,
            "symbol": settings.phase0_symbol,
            "provider": settings.provider,
            "mode": "live",
            "user_id": session.user_id,
            "counts": counts,
            "stress_window": "1d",
            "artifact_paths": artifact_paths,
            "seal_lag_seconds": args.seal_lag_seconds,
            "duration_minutes": args.duration_minutes,
        }
        artifact_paths["report"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_live_report", report, now)
        )
        artifact_paths["manifest"] = _artifact_ref(
            write_json_artifact(
                settings.artifacts_dir,
                "phase0_live_manifest",
                _manifest_payload(
                    settings,
                    "live",
                    session.user_id,
                    counts,
                    artifact_paths,
                    now,
                    extra_config={
                        "duration_minutes": args.duration_minutes,
                        "seal_lag_seconds": args.seal_lag_seconds,
                    },
                ),
                now,
            )
        )
        print("Live validation complete.")
        return 0
    except Exception as exc:
        _record_stage_failure(db, run_id, stage, exc, {"stress_window": "1d"})
        raise
    finally:
        _finish_db_run(db, db_context, run_id, report, stage, counts, artifact_paths, settings, "live", session.user_id)


def run_replay(settings, args) -> int:
    ensure_dir(settings.artifacts_dir)
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = _base_counts()
    counts["replayed_ticks"] = 0
    artifact_paths: Dict[str, str] = {"source_manifest": _artifact_ref(manifest_path)}
    report = None
    stage = "replay"
    allow_ltp = getattr(args, "allow_ltp_fallback", False)

    db, db_context, run_id = _start_db_run(
        settings,
        skip_db=args.skip_db,
        probe_name="phase0_replay",
        mode="replay",
        user_id=manifest.get("user_id") or "",
    )

    try:
        universe_rows = json.loads(Path(manifest["artifact_paths"]["universe"]).read_text(encoding="utf-8"))
        universe = universe_items_from_rows(universe_rows)
        accumulator = MinuteAccumulator(
            universe,
            manifest["config"].get("risk_free_rate", settings.risk_free_rate),
            allow_ltp_fallback=allow_ltp,
            strike_step=settings.strike_step,
        )

        expected_underlying = read_jsonl(Path(manifest["artifact_paths"]["sealed_underlying"]))
        expected_options = read_jsonl(Path(manifest["artifact_paths"]["sealed_options"]))
        expected_nodes = read_jsonl(Path(manifest["artifact_paths"]["sealed_expiry_nodes"]))
        tick_rows = read_jsonl(Path(manifest["artifact_paths"]["raw_ticks"]))

        actual_underlying: List[Dict] = []
        actual_options: List[Dict] = []
        actual_nodes: List[Dict] = []
        last_received_at = None
        seal_lag_seconds = int(manifest["config"].get("seal_lag_seconds", 2))
        for tick_row in tick_rows:
            received_at = ensure_ist(tick_row["received_at"])
            tick = _rehydrate_tick(tick_row["tick"])
            accumulator.feed_ticks([tick], received_at)
            counts["replayed_ticks"] += 1
            for result in accumulator.seal_ready(received_at, seal_lag_seconds):
                actual_underlying.extend(result.underlying_rows)
                actual_options.extend(result.option_rows)
                actual_nodes.extend(result.expiry_node_rows)
            last_received_at = received_at

        flush_at = (last_received_at or datetime.now(IST)) + timedelta(minutes=2)
        for result in accumulator.seal_ready(flush_at, seal_lag_seconds):
            actual_underlying.extend(result.underlying_rows)
            actual_options.extend(result.option_rows)
            actual_nodes.extend(result.expiry_node_rows)

        counts["underlying_snapshots"] = len(actual_underlying)
        counts["option_snapshots"] = len(actual_options)
        counts["expiry_nodes"] = len(actual_nodes)

        underlying_compare = compare_row_sets(expected_underlying, actual_underlying, ("ts", "tradingsymbol"))
        option_compare = compare_row_sets(expected_options, actual_options, ("ts", "tradingsymbol"))
        node_compare = compare_row_sets(expected_nodes, actual_nodes, ("ts", "expiry"))

        if db:
            db.upsert_underlying_snapshots(actual_underlying)
            db.upsert_option_snapshots(actual_options)
            db.upsert_expiry_nodes(actual_nodes)
            db.commit()

        report = {
            "run_id": run_id,
            "mode": "replay",
            "symbol": manifest.get("symbol", settings.phase0_symbol),
            "user_id": manifest.get("user_id"),
            "counts": counts,
            "stress_window": "1d",
            "comparisons": {
                "underlying": underlying_compare,
                "options": option_compare,
                "expiry_nodes": node_compare,
            },
            "artifact_paths": artifact_paths,
            "ok": all(section["ok"] for section in (underlying_compare, option_compare, node_compare)),
        }
        artifact_paths["report"] = _artifact_ref(
            write_json_artifact(settings.artifacts_dir, "phase0_replay_report", report, datetime.now(IST))
        )
        if not report["ok"]:
            raise RuntimeError("Replay output does not match the saved live artifacts.")

        print("Replay validation complete.")
        return 0
    except Exception as exc:
        _record_stage_failure(db, run_id, "replay", exc, {"stress_window": "1d"})
        raise
    finally:
        _finish_db_run(db, db_context, run_id, report, stage, counts, artifact_paths, settings, "replay", manifest.get("user_id"))


def run_history_probe(settings, args) -> int:
    provider = get_provider(settings)
    provider.ensure_session(settings)

    print("Fetching expired expiries for %s..." % settings.spot_instrument_key)
    expiries = provider.get_expired_expiries(settings.spot_instrument_key)
    print("Found %d expired expiries." % len(expiries))
    for expiry in expiries[:10]:
        print("  %s" % expiry)
        contracts = provider.get_expired_option_contracts(settings.spot_instrument_key, expiry)
        print("    -> %d contracts" % len(contracts))
        if contracts:
            sample = contracts[0]
            expired_key = sample.get("expired_instrument_key") or sample.get("instrument_key") or ""
            if expired_key:
                candles = provider.fetch_expired_history(expired_key, interval="day")
                print("    -> %d candles for %s" % (len(candles), expired_key))

    print("History probe complete.")
    return 0


def _collect_ready_minutes(accumulator: MinuteAccumulator, lock: threading.Lock, seal_lag_seconds: int):
    with lock:
        return accumulator.seal_ready(datetime.now(IST), seal_lag_seconds)


def _persist_sealed_result(result, underlying_path: Path, option_path: Path, node_path: Path) -> None:
    for row in result.underlying_rows:
        append_jsonl(underlying_path, row)
    for row in result.option_rows:
        append_jsonl(option_path, row)
    for row in result.expiry_node_rows:
        append_jsonl(node_path, row)


def _rehydrate_tick(payload: Dict) -> Dict:
    tick = dict(payload)
    for key in ("exchange_timestamp", "last_trade_time"):
        value = tick.get(key)
        if isinstance(value, str):
            tick[key] = ensure_ist(value)
    return tick


def _manifest_payload(
    settings,
    mode: str,
    user_id: Optional[str],
    counts: Dict,
    artifact_paths: Dict[str, str],
    now: datetime,
    extra_config: Optional[Dict] = None,
) -> Dict:
    config = {
        "phase0_symbol": settings.phase0_symbol,
        "spot_instrument_key": settings.spot_instrument_key,
        "provider": settings.provider,
        "risk_free_rate": settings.risk_free_rate,
    }
    if extra_config:
        config.update(extra_config)
    return {
        "as_of": now,
        "symbol": settings.phase0_symbol,
        "mode": mode,
        "user_id": user_id,
        "counts": counts,
        "artifact_paths": artifact_paths,
        "stress_window": "1d",
        "config": config,
    }


def _base_counts() -> Dict[str, int]:
    return {
        "nifty_instruments": 0,
        "universe_items": 0,
        "quote_payloads": 0,
        "historical_series": 0,
        "underlying_snapshots": 0,
        "option_snapshots": 0,
        "expiry_nodes": 0,
    }


def _future_price_from_rows(universe, underlying_rows: Sequence[Dict]) -> Optional[float]:
    front_key = next((item.instrument_key for item in universe if item.role == "future_front"), None)
    for row in underlying_rows:
        if front_key is not None and row.get("instrument_key") == front_key and row.get("last_price") is not None:
            return float(row["last_price"])
    for row in underlying_rows:
        if row.get("source_type") == "future" and row.get("last_price") is not None:
            return float(row["last_price"])
    return None


def _artifact_ref(path: Path) -> str:
    return str(path.resolve())


def _start_db_run(settings, skip_db: bool, probe_name: str, mode: str, user_id: str):
    if skip_db or not settings.supabase_db_url:
        return None, None, str(uuid.uuid4())

    details = {
        "symbol": settings.phase0_symbol,
        "mode": mode,
        "provider": settings.provider,
        "user_id": user_id,
        "counts": _base_counts(),
        "artifact_paths": {},
        "stress_window": "1d",
    }
    db_context = Phase0Database(settings.supabase_db_url)
    db = db_context.__enter__()
    run_id = db.start_probe_run(probe_name=probe_name, started_at=datetime.now(IST), details=details, session_user_id=user_id)
    db.commit()
    return db, db_context, run_id


def _record_stage_failure(db, run_id: str, stage: str, exc: Exception, payload: Dict) -> None:
    if not db:
        return
    db.record_probe_event(run_id=run_id, stage=stage, message=str(exc), payload=payload)
    db.commit()


def _finish_db_run(
    db,
    db_context,
    run_id: str,
    report: Optional[Dict],
    stage: str,
    counts: Dict,
    artifact_paths: Dict[str, str],
    settings,
    mode: str,
    user_id: Optional[str],
) -> None:
    if not db or not db_context:
        return
    final_details = report or {
        "symbol": settings.phase0_symbol,
        "mode": mode,
        "user_id": user_id,
        "counts": counts,
        "artifact_paths": artifact_paths,
        "stress_window": "1d",
        "failed_stage": stage,
    }
    status = "completed" if report else "failed"
    db.finish_probe_run(run_id=run_id, ended_at=datetime.now(IST), status=status, details=final_details)
    db_context.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
