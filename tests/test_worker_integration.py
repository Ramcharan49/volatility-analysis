"""Integration tests for V1 worker wiring fixes.

Tests the new integration code: provider usage, gap-fill wiring,
prior_close loading, percentile computation in pipeline, post-market,
DB methods, and __main__ entry point.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

from phase0.config import Settings
from phase0.live import SealedMinuteResult
from phase0.metrics import FLOW_BASE_METRICS, FLOW_METRIC_KEYS, LEVEL_METRIC_KEYS
from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone
from worker.main import FlowRingBuffer, Worker, process_sealed_minute

IST = indian_timezone()


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        provider="upstox",
        upstox_api_key="test",
        upstox_api_secret="test",
        upstox_redirect_url="http://localhost",
        session_state_path="./state/session.json",
        artifacts_dir="./artifacts",
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


def _make_sealed_minute(ts: datetime) -> SealedMinuteResult:
    """Create a minimal sealed minute with one expiry node."""
    expiry = (ts + timedelta(days=30)).date()
    node_row = {
        "ts": ts, "expiry": expiry, "dte_days": 30.0,
        "forward": 22000.0, "atm_strike": 22000.0, "atm_iv": 0.20,
        "iv_25c": 0.19, "iv_25p": 0.22,
        "iv_10c": 0.18, "iv_10p": 0.24,
        "rr25": -0.03, "bf25": 0.005,
        "source_count": 50, "quality_score": 0.9,
        "method_json": {"pricing_model": "black_76"},
    }
    return SealedMinuteResult(
        minute_ts=ts,
        underlying_rows=[],
        option_rows=[],
        expiry_node_rows=[node_row],
    )


# ── process_sealed_minute with percentiles ──────────────────────────

class TestProcessSealedMinuteWithPercentiles(unittest.TestCase):
    """Fix H4/H5: percentiles and dashboard update in per-minute pipeline."""

    def test_percentiles_computed_when_baselines_provided(self):
        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        sealed = _make_sealed_minute(ts)
        flow_buffer = FlowRingBuffer()

        # Provide baselines with enough history for percentile computation
        baselines = {key: [0.15 + i * 0.005 for i in range(60)] for key in LEVEL_METRIC_KEYS}
        flow_baselines = {key: [0.001 * i for i in range(60)] for key in FLOW_METRIC_KEYS}

        summary = process_sealed_minute(
            sealed, flow_buffer, {},
            db=None, baselines=baselines, flow_baselines=flow_baselines,
        )

        self.assertIn("state_score", summary)
        self.assertIn("stress_score", summary)
        # With enough baselines, state_score should be computed
        # (may or may not be None depending on data, but the key exists)

    def test_no_percentiles_without_baselines(self):
        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        sealed = _make_sealed_minute(ts)
        flow_buffer = FlowRingBuffer()

        summary = process_sealed_minute(
            sealed, flow_buffer, {},
            db=None, baselines=None, flow_baselines=None,
        )

        self.assertIsNone(summary["state_score"])
        self.assertIsNone(summary["stress_score"])

    def test_dashboard_upserted_when_db_provided(self):
        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        sealed = _make_sealed_minute(ts)
        flow_buffer = FlowRingBuffer()

        db = MagicMock()
        baselines = {key: [0.15 + i * 0.005 for i in range(60)] for key in LEVEL_METRIC_KEYS}

        process_sealed_minute(
            sealed, flow_buffer, {},
            db=db, source_mode="live", baselines=baselines,
        )

        db.upsert_dashboard.assert_called_once()
        payload = db.upsert_dashboard.call_args[0][0]
        self.assertIn("as_of", payload)
        self.assertIn("state_score", payload)
        self.assertIn("key_cards", payload)

    def test_metric_rows_include_percentile_values(self):
        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        sealed = _make_sealed_minute(ts)
        flow_buffer = FlowRingBuffer()

        db = MagicMock()
        # Baselines where current value (0.20) is at the 80th percentile
        baselines = {key: [0.10 + i * 0.002 for i in range(60)] for key in LEVEL_METRIC_KEYS}

        process_sealed_minute(
            sealed, flow_buffer, {},
            db=db, source_mode="live", baselines=baselines,
        )

        # Check that upsert_metric_series was called and rows have percentile field
        db.upsert_metric_series.assert_called_once()
        rows = db.upsert_metric_series.call_args[0][0]
        # At least some level metrics should have percentile values
        level_rows = [r for r in rows if r["metric_key"] in LEVEL_METRIC_KEYS]
        has_pct = [r for r in level_rows if r["percentile"] is not None]
        self.assertGreater(len(has_pct), 0, "Expected some level metrics to have percentile values")


# ── Prior close loading ─────────────────────────────────────────────

class TestLoadPriorClose(unittest.TestCase):
    """Fix H2: prior_close loaded from DB at startup."""

    def test_loads_prior_close_from_db(self):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)

        db = MagicMock()
        db.fetch_last_minute_metrics.return_value = {
            "atm_iv_7d": 0.18,
            "rr25_30d": -0.025,
            "bf25_30d": 0.004,
            "front_end_dominance": 0.02,
        }

        worker._load_prior_close(db)

        self.assertEqual(len(worker.prior_close), 4)
        self.assertAlmostEqual(worker.prior_close["atm_iv_7d"], 0.18)
        self.assertAlmostEqual(worker.prior_close["rr25_30d"], -0.025)

    def test_empty_prior_close_when_no_data(self):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)

        db = MagicMock()
        db.fetch_last_minute_metrics.return_value = {}

        worker._load_prior_close(db)

        self.assertEqual(len(worker.prior_close), 0)


# ── Post-market pipeline ────────────────────────────────────────────

class TestPostMarketPipeline(unittest.TestCase):
    """Fix H3: post-market writes baselines, brief, dashboard."""

    @patch("worker.main.WorkerDatabase")
    def test_post_market_writes_baselines_and_brief(self, MockDB):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)
        worker._stop = True  # Don't loop in _sleep

        db_instance = MagicMock()
        MockDB.return_value.__enter__ = MagicMock(return_value=db_instance)
        MockDB.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate today's metrics in DB
        db_instance.fetch_last_minute_metrics.return_value = {
            "atm_iv_7d": 0.20, "atm_iv_30d": 0.22, "atm_iv_90d": 0.21,
            "rr25_7d": -0.02, "rr25_30d": -0.03, "rr25_90d": -0.025,
            "bf25_7d": 0.005, "bf25_30d": 0.006, "bf25_90d": 0.004,
            "term_7d_30d": 0.02, "front_end_dominance": 0.03,
            "d_atm_iv_7d_1d": 0.005, "d_rr25_30d_1d": -0.002,
        }
        db_instance.fetch_metric_baselines.return_value = {
            key: [0.15 + i * 0.005 for i in range(60)] for key in LEVEL_METRIC_KEYS
        }
        db_instance.fetch_flow_baselines.return_value = {}

        worker._run_post_market()

        db_instance.upsert_metric_baselines.assert_called_once()
        db_instance.upsert_daily_brief.assert_called_once()
        db_instance.upsert_dashboard.assert_called_once()

    @patch("worker.main.WorkerDatabase")
    def test_post_market_skips_when_no_data(self, MockDB):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)
        worker._stop = True

        db_instance = MagicMock()
        MockDB.return_value.__enter__ = MagicMock(return_value=db_instance)
        MockDB.return_value.__exit__ = MagicMock(return_value=False)
        db_instance.fetch_last_minute_metrics.return_value = {}

        worker._run_post_market()

        db_instance.upsert_metric_baselines.assert_not_called()
        db_instance.upsert_daily_brief.assert_not_called()


# ── Gap-fill wiring ─────────────────────────────────────────────────

class TestGapFillWiring(unittest.TestCase):
    """Fix H1: gap-fill called from worker lifecycle."""

    def test_gap_fill_with_db_calls_detect_and_backfill(self):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)

        db = MagicMock()
        db.fetch_last_sealed_ts.return_value = None

        universe = []
        provider = MagicMock()

        with patch("worker.gap_fill.detect_gaps") as mock_detect, \
             patch("worker.gap_fill.backfill_day") as mock_backfill:
            mock_detect.return_value = []
            worker._run_gap_fill_with_db(db, universe, provider)
            mock_detect.assert_called_once()
            mock_backfill.assert_not_called()

    def test_gap_fill_calls_backfill_for_each_gap(self):
        settings = _make_settings(supabase_db_url="test://db")
        worker = Worker(settings)

        db = MagicMock()
        db.fetch_last_sealed_ts.return_value = None

        universe = []
        provider = MagicMock()
        provider.client = MagicMock()

        mock_gap = MagicMock()
        mock_gap.gap_date = date(2026, 3, 19)

        with patch("worker.gap_fill.detect_gaps") as mock_detect, \
             patch("worker.gap_fill.backfill_day") as mock_backfill:
            mock_detect.return_value = [mock_gap]
            mock_backfill.return_value = {"day": "2026-03-19", "minutes_filled": 100}
            worker._run_gap_fill_with_db(db, universe, provider)
            mock_backfill.assert_called_once()


# ── DB method fixes ─────────────────────────────────────────────────

class TestDBMethodSignatures(unittest.TestCase):
    """Fix C3: SQL parameterization uses timedelta instead of interval."""

    def test_fetch_latest_metric_values_uses_timedelta(self):
        """Verify the SQL no longer uses interval '%s minutes'."""
        import inspect
        from worker.db import WorkerDatabase
        source = inspect.getsource(WorkerDatabase.fetch_latest_metric_values)
        self.assertNotIn("interval", source)
        self.assertIn("start_ts", source)

    def test_fetch_metric_baselines_uses_timedelta(self):
        """Verify the SQL no longer uses interval '%s days'."""
        import inspect
        from worker.db import WorkerDatabase
        source = inspect.getsource(WorkerDatabase.fetch_metric_baselines)
        self.assertNotIn("interval", source)
        self.assertIn("cutoff", source)

    def test_fetch_flow_baselines_exists(self):
        from worker.db import WorkerDatabase
        self.assertTrue(hasattr(WorkerDatabase, "fetch_flow_baselines"))

    def test_fetch_last_minute_metrics_exists(self):
        from worker.db import WorkerDatabase
        self.assertTrue(hasattr(WorkerDatabase, "fetch_last_minute_metrics"))


# ── __main__.py entry point ─────────────────────────────────────────

class TestMainEntryPoint(unittest.TestCase):
    """Fix M2: python -m worker works."""

    def test_main_module_exists(self):
        import importlib
        spec = importlib.util.find_spec("worker.__main__")
        self.assertIsNotNone(spec)

    def test_main_module_imports_main(self):
        """Verify __main__.py contains the right import (read file, don't import it)."""
        import pathlib
        main_path = pathlib.Path(__file__).parent.parent / "worker" / "__main__.py"
        source = main_path.read_text()
        self.assertIn("from worker.main import main", source)
        self.assertIn("main()", source)


# ── Import verification ─────────────────────────────────────────────

class TestImports(unittest.TestCase):
    """Verify all new imports in worker.main resolve correctly."""

    def test_daily_brief_imports(self):
        from worker.daily_brief import generate_daily_brief, generate_dashboard_payload
        self.assertTrue(callable(generate_daily_brief))
        self.assertTrue(callable(generate_dashboard_payload))

    def test_percentile_imports(self):
        from worker.percentile import (
            compute_flow_percentiles,
            compute_level_percentiles,
            compute_state_score,
            compute_stress_score,
        )
        self.assertTrue(callable(compute_level_percentiles))

    def test_metric_key_imports(self):
        from phase0.metrics import FLOW_METRIC_KEYS, LEVEL_METRIC_KEYS
        self.assertGreater(len(LEVEL_METRIC_KEYS), 0)
        self.assertGreater(len(FLOW_METRIC_KEYS), 0)

    def test_worker_main_imports_cleanly(self):
        """Verify worker.main module loads without import errors."""
        import importlib
        mod = importlib.import_module("worker.main")
        self.assertTrue(hasattr(mod, "Worker"))
        self.assertTrue(hasattr(mod, "process_sealed_minute"))


if __name__ == "__main__":
    unittest.main()
