"""Backfill multiple days of history data into the database.

Usage:
  # Full 375-minute backfill for all days
  python backfill.py --from 2026-03-24 --to 2026-04-02

  # Daily-close-only for all days (fast)
  python backfill.py --from 2025-04-01 --to 2026-03-01 --mode daily

  # Hybrid: daily before cutoff, full after (recommended)
  python backfill.py --from 2025-04-01 --to 2026-04-02 --daily-before 2026-03-01

  # Skip DB (CSV export only)
  python backfill.py --from 2026-03-24 --to 2026-04-02 --skip-db
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional

from phase0.artifacts import ensure_dir, write_json
from phase0.config import load_settings
from verify_pipeline import run_history, run_history_daily
from worker.calendar import trading_days_between
from worker.db import WorkerDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _is_non_fatal_outcome(outcome: BackfillDayOutcome) -> bool:
    return outcome.status in {"completed", "partial"} or (
        outcome.mode == "daily" and outcome.status == "no_data"
    )


@dataclass(frozen=True)
class BackfillDayOutcome:
    day: date
    mode: str
    source: str
    status: str
    persisted: bool
    skip_db: bool
    elapsed_sec: float
    row_counts: Dict[str, int]
    outputs: Dict[str, int]
    message: str
    artifact_dir: Optional[str]
    diagnostics: Dict[str, object] = field(default_factory=dict)


def _run_day(day, mode, settings, skip_db, daily_source=None) -> BackfillDayOutcome:
    """Run a single day's backfill and return a structured outcome."""
    args = SimpleNamespace(date=day.isoformat(), skip_db=skip_db, source=daily_source)
    runner = run_history_daily if mode == "daily" else run_history
    start = time.monotonic()
    rc = runner(settings, args)
    elapsed = time.monotonic() - start
    pipeline_outcome = getattr(args, "_outcome", None)
    if pipeline_outcome is not None:
        return BackfillDayOutcome(
            day=day,
            mode=mode,
            source=getattr(pipeline_outcome, "source", daily_source or "upstox"),
            status=pipeline_outcome.status,
            persisted=pipeline_outcome.persisted,
            skip_db=skip_db,
            elapsed_sec=elapsed,
            row_counts=dict(getattr(pipeline_outcome, "row_counts", {}) or {}),
            outputs=dict(getattr(pipeline_outcome, "outputs", {}) or {}),
            message=pipeline_outcome.message,
            artifact_dir=getattr(pipeline_outcome, "artifact_dir", None),
            diagnostics=dict(getattr(pipeline_outcome, "diagnostics", {}) or {}),
        )
    return BackfillDayOutcome(
        day=day,
        mode=mode,
        source=daily_source or "upstox",
        status="completed" if rc == 0 else "source_error",
        persisted=not skip_db and rc == 0,
        skip_db=skip_db,
        elapsed_sec=elapsed,
        row_counts={},
        outputs={},
        message="runner returned rc=%d" % rc,
        artifact_dir=None,
        diagnostics={},
    )


def _write_backfill_manifest(settings, start: date, end: date, outcomes) -> Optional[Path]:
    if not outcomes:
        return None
    now = time.strftime("%Y%m%d_%H%M%S")
    out_dir = settings.artifacts_dir / ("backfill_%s_%s_%s" % (start.isoformat(), end.isoformat(), now))
    ensure_dir(out_dir)
    manifest = {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }
    return write_json(out_dir / "manifest.json", manifest)


def _build_summary(start: date, end: date, outcomes, manifest_path: Optional[Path]) -> Dict[str, object]:
    status_counts: Dict[str, int] = {}
    persisted_days = 0
    partial_days = 0
    no_data_days = 0
    output_rows = 0
    for outcome in outcomes:
        status_counts[outcome.status] = status_counts.get(outcome.status, 0) + 1
        if outcome.persisted:
            persisted_days += 1
        if outcome.status == "partial":
            partial_days += 1
        if outcome.status == "no_data":
            no_data_days += 1
        output_rows += sum(int(v) for v in outcome.outputs.values())

    succeeded = [o for o in outcomes if _is_non_fatal_outcome(o)]
    failed = [o for o in outcomes if not _is_non_fatal_outcome(o)]
    return {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "total_days": len(outcomes),
        "succeeded_days": len(succeeded),
        "failed_days": len(failed),
        "partial_days": partial_days,
        "no_data_days": no_data_days,
        "persisted_days": persisted_days,
        "status_counts": status_counts,
        "output_rows": output_rows,
        "failed_dates": [o.day.isoformat() for o in failed],
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
    }


def _insert_history_audit_run(settings, start: date, end: date,
                              daily_source: str, skip_db: bool) -> Optional[str]:
    if skip_db or not settings.supabase_db_url:
        return None
    try:
        with WorkerDatabase(settings.supabase_db_url) as db:
            run_id = db.insert_history_backfill_run(start, end, daily_source, skip_db)
            db.commit()
            return run_id
    except Exception as exc:
        log.warning("History audit setup failed: %s", exc)
        return None


def _write_history_audit_day(settings, run_id: Optional[str], outcome: BackfillDayOutcome) -> None:
    if not run_id or not settings.supabase_db_url:
        return
    try:
        with WorkerDatabase(settings.supabase_db_url) as db:
            db.upsert_history_backfill_day_log(run_id, asdict(outcome))
            db.commit()
    except Exception as exc:
        log.warning("History audit day write failed for %s: %s", outcome.day, exc)


def _finalize_history_audit_run(settings, run_id: Optional[str], status: str,
                                summary: Dict[str, object]) -> None:
    if not run_id or not settings.supabase_db_url:
        return
    try:
        with WorkerDatabase(settings.supabase_db_url) as db:
            db.update_history_backfill_run(run_id, status, summary)
            db.commit()
    except Exception as exc:
        log.warning("History audit finalize failed: %s", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill history for a date range")
    parser.add_argument("--from", dest="from_date", required=True,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", required=True,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--mode", choices=["full", "daily"], default="full",
                        help="full = 375 min/day (default), daily = close-only")
    parser.add_argument("--daily-before", dest="daily_before",
                        help="Hybrid: use daily mode before this date, full after (YYYY-MM-DD)")
    parser.add_argument("--daily-source", choices=["nse_udiff", "upstox"],
                        help="Daily history source for daily-mode dates")
    parser.add_argument("--skip-db", action="store_true",
                        help="Skip DB writes (CSV export only)")
    cli = parser.parse_args()

    start = date.fromisoformat(cli.from_date)
    end = date.fromisoformat(cli.to_date)
    daily_cutoff = date.fromisoformat(cli.daily_before) if cli.daily_before else None

    if start > end:
        log.error("--from (%s) must be <= --to (%s)", start, end)
        return 1

    days = trading_days_between(start, end)
    if not days:
        log.error("No trading days in range %s to %s", start, end)
        return 1

    # Build schedule: list of (day, mode) tuples
    schedule = []
    for day in days:
        if daily_cutoff and day < daily_cutoff:
            schedule.append((day, "daily"))
        elif cli.mode == "daily":
            schedule.append((day, "daily"))
        else:
            schedule.append((day, "full"))

    daily_count = sum(1 for _, m in schedule if m == "daily")
    full_count = sum(1 for _, m in schedule if m == "full")
    log.info("Backfill: %s to %s — %d daily-close + %d full-minute = %d total trading days",
             start, end, daily_count, full_count, len(schedule))

    settings = load_settings()
    effective_daily_source = cli.daily_source or settings.daily_history_source
    run_id = _insert_history_audit_run(
        settings,
        start,
        end,
        effective_daily_source,
        cli.skip_db,
    )
    outcomes = []
    total_start = time.monotonic()

    for i, (day, mode) in enumerate(schedule, 1):
        label = "daily close" if mode == "daily" else "full 375 min"
        log.info("=== [%d/%d] %s (%s) ===", i, len(schedule), day, label)

        try:
            outcome = _run_day(day, mode, settings, cli.skip_db, cli.daily_source)
            outcomes.append(outcome)
            _write_history_audit_day(settings, run_id, outcome)
            if _is_non_fatal_outcome(outcome):
                log.info("=== %s %s in %.1f min ===", day, outcome.status, outcome.elapsed_sec / 60)
            else:
                log.warning("=== %s %s in %.1f min: %s ===",
                            day, outcome.status, outcome.elapsed_sec / 60, outcome.message)
        except Exception as exc:
            outcome = BackfillDayOutcome(
                day=day,
                mode=mode,
                source=cli.daily_source or settings.daily_history_source,
                status="source_error",
                persisted=False,
                skip_db=cli.skip_db,
                elapsed_sec=0.0,
                row_counts={},
                outputs={},
                message=str(exc),
                artifact_dir=None,
                diagnostics={},
            )
            outcomes.append(outcome)
            _write_history_audit_day(settings, run_id, outcome)
            log.error("=== %s failed: %s ===", day, exc)

    total_elapsed = time.monotonic() - total_start
    succeeded = [o for o in outcomes if _is_non_fatal_outcome(o)]
    failed = [o for o in outcomes if not _is_non_fatal_outcome(o)]
    manifest_path = _write_backfill_manifest(settings, start, end, outcomes)
    summary = _build_summary(start, end, outcomes, manifest_path)
    summary["elapsed_sec"] = round(total_elapsed, 3)
    final_status = "completed" if not failed else ("partial" if succeeded else "failed")
    _finalize_history_audit_run(settings, run_id, final_status, summary)
    log.info("──────────────────────────────────────")
    log.info("Backfill complete: %d succeeded, %d failed, %.1f min total",
             len(succeeded), len(failed), total_elapsed / 60)
    if failed:
        log.warning("Failed dates: %s", ", ".join(str(o.day) for o in failed))
    if manifest_path is not None:
        log.info("Backfill manifest written to %s", manifest_path)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
