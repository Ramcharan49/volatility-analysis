"""Backfill multiple days of history data into the database.

Usage:
  python backfill.py --from 2026-03-24 --to 2026-04-02
  python backfill.py --from 2026-03-24 --to 2026-04-02 --skip-db
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from types import SimpleNamespace

from phase0.config import load_settings
from verify_pipeline import run_history
from worker.calendar import trading_days_between

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill history for a date range")
    parser.add_argument("--from", dest="from_date", required=True,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", required=True,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--skip-db", action="store_true",
                        help="Skip DB writes (CSV export only)")
    cli = parser.parse_args()

    start = date.fromisoformat(cli.from_date)
    end = date.fromisoformat(cli.to_date)

    if start > end:
        log.error("--from (%s) must be <= --to (%s)", start, end)
        return 1

    days = trading_days_between(start, end)
    if not days:
        log.error("No trading days in range %s to %s", start, end)
        return 1

    log.info("Backfill range: %s to %s (%d trading days)", start, end, len(days))

    settings = load_settings()
    succeeded = []
    failed = []
    total_start = time.monotonic()

    for i, day in enumerate(days, 1):
        log.info("=== [%d/%d] Processing %s ===", i, len(days), day)
        day_start = time.monotonic()

        args = SimpleNamespace(date=day.isoformat(), skip_db=cli.skip_db)
        try:
            rc = run_history(settings, args)
            elapsed = time.monotonic() - day_start
            if rc == 0:
                succeeded.append(day)
                log.info("=== %s completed in %.1f min ===", day, elapsed / 60)
            else:
                failed.append(day)
                log.warning("=== %s finished with errors (rc=%d) in %.1f min ===",
                            day, rc, elapsed / 60)
        except Exception as exc:
            elapsed = time.monotonic() - day_start
            failed.append(day)
            log.error("=== %s failed after %.1f min: %s ===", day, elapsed / 60, exc)

    total_elapsed = time.monotonic() - total_start
    log.info("──────────────────────────────────────")
    log.info("Backfill complete: %d succeeded, %d failed, %.1f min total",
             len(succeeded), len(failed), total_elapsed / 60)
    if failed:
        log.warning("Failed dates: %s", ", ".join(str(d) for d in failed))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
