from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from phase0.config import Settings


def _make_settings(**overrides) -> Settings:
    tmpdir = Path(tempfile.mkdtemp())
    defaults = dict(
        provider="upstox",
        upstox_api_key="test",
        upstox_api_secret="test",
        upstox_redirect_url="http://localhost",
        session_state_path=tmpdir / "session.json",
        artifacts_dir=tmpdir / "artifacts",
        risk_free_rate=0.06,
        phase0_symbol="NIFTY",
        spot_instrument_key="NSE_INDEX|Nifty 50",
        derivative_segment="NSE_FO",
        store_raw_json_in_db=False,
        expired_history_months=6,
        supabase_db_url=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestBackfillRangeBehavior(unittest.TestCase):
    def test_main_continues_when_one_date_has_no_data(self):
        import backfill

        days = [date(2026, 4, 1), date(2026, 4, 2)]
        no_data = backfill.BackfillDayOutcome(
            day=days[0],
            mode="daily",
            source="nse_udiff",
            status="no_data",
            persisted=False,
            skip_db=True,
            elapsed_sec=0.2,
            row_counts={},
            outputs={},
            message="no usable option rows",
            artifact_dir=None,
        )
        completed = backfill.BackfillDayOutcome(
            day=days[1],
            mode="daily",
            source="nse_udiff",
            status="completed",
            persisted=False,
            skip_db=True,
            elapsed_sec=0.2,
            row_counts={"option_rows": 20},
            outputs={"expiry_nodes": 3},
            message="ok",
            artifact_dir=None,
        )

        with patch("backfill.trading_days_between", return_value=days), \
             patch("backfill.load_settings", return_value=_make_settings()), \
             patch("backfill._run_day", side_effect=[no_data, completed]) as mock_run, \
             patch("sys.argv", ["backfill.py", "--from", "2026-04-01", "--to", "2026-04-02", "--mode", "daily", "--skip-db"]):
            rc = backfill.main()

        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(rc, 0)

    def test_partial_and_completed_dates_return_success(self):
        import backfill

        days = [date(2026, 4, 1), date(2026, 4, 2)]
        partial = backfill.BackfillDayOutcome(
            day=days[0],
            mode="daily",
            source="nse_udiff",
            status="partial",
            persisted=True,
            skip_db=False,
            elapsed_sec=0.2,
            row_counts={"option_rows": 10},
            outputs={"expiry_nodes": 1},
            message="missing far tenor",
            artifact_dir=None,
        )
        completed = backfill.BackfillDayOutcome(
            day=days[1],
            mode="daily",
            source="nse_udiff",
            status="completed",
            persisted=True,
            skip_db=False,
            elapsed_sec=0.2,
            row_counts={"option_rows": 20},
            outputs={"expiry_nodes": 3},
            message="ok",
            artifact_dir=None,
        )

        with patch("backfill.trading_days_between", return_value=days), \
             patch("backfill.load_settings", return_value=_make_settings()), \
             patch("backfill._run_day", side_effect=[partial, completed]), \
             patch("sys.argv", ["backfill.py", "--from", "2026-04-01", "--to", "2026-04-02", "--mode", "daily"]):
            rc = backfill.main()

        self.assertEqual(rc, 0)

    def test_main_writes_db_audit_rows_when_db_enabled(self):
        import backfill

        day = date(2026, 4, 2)
        completed = backfill.BackfillDayOutcome(
            day=day,
            mode="daily",
            source="nse_udiff",
            status="completed",
            persisted=True,
            skip_db=False,
            elapsed_sec=0.2,
            row_counts={"option_rows": 20},
            outputs={"expiry_nodes": 3},
            message="ok",
            artifact_dir="artifacts/verify_daily_nse_udiff_2026-04-02",
        )

        settings = _make_settings(supabase_db_url="test://db")

        with patch("backfill.trading_days_between", return_value=[day]), \
             patch("backfill.load_settings", return_value=settings), \
             patch("backfill._run_day", return_value=completed), \
             patch("backfill.WorkerDatabase") as MockDB, \
             patch("sys.argv", ["backfill.py", "--from", "2026-04-02", "--to", "2026-04-02", "--mode", "daily"]):
            db = MockDB.return_value.__enter__.return_value
            rc = backfill.main()

        self.assertEqual(rc, 0)
        db.insert_history_backfill_run.assert_called_once()
        db.upsert_history_backfill_day_log.assert_called_once()
        db.update_history_backfill_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
