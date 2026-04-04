from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from phase0.config import Settings
from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone


IST = indian_timezone()


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
        strike_step=100.0,
        strikes_around_atm=15,
        daily_history_source="nse_udiff",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _fake_pipeline_result(ts: datetime) -> dict:
    cm_node = SimpleNamespace(
        tenor_code="7d",
        tenor_days=7,
        atm_iv=0.20,
        iv_25c=0.19,
        iv_25p=0.21,
        iv_10c=None,
        iv_10p=None,
        rr25=-0.02,
        bf25=0.001,
        quality="single_expiry",
        bracket_expiries=[],
    )
    return {
        "ts": ts,
        "cm_nodes": [cm_node],
        "level_points": [],
        "flow_points": [],
        "surface_cells": [],
        "level_dict": {
            "atm_iv_7d": 0.20,
            "atm_iv_30d": None,
            "atm_iv_90d": None,
            "rr25_30d": None,
            "bf25_30d": None,
        },
        "flow_dict": {},
        "level_pcts": {},
        "flow_pcts": {},
        "state_score": None,
        "stress_score": None,
        "quadrant": None,
    }


def _fake_pipeline_result_with_points(ts: datetime) -> dict:
    cm_node = SimpleNamespace(
        tenor_code="7d",
        tenor_days=7,
        atm_iv=0.20,
        iv_25c=0.19,
        iv_25p=0.21,
        iv_10c=None,
        iv_10p=None,
        rr25=-0.02,
        bf25=0.001,
        quality="single_expiry",
        bracket_expiries=[],
    )
    level_point = SimpleNamespace(ts=ts, metric_key="atm_iv_7d", tenor_code="7d", value=0.20)
    flow_point = SimpleNamespace(ts=ts, metric_key="d_atm_iv_7d_1d", window_code="1d", value=0.01)
    return {
        "ts": ts,
        "cm_nodes": [cm_node],
        "level_points": [level_point],
        "flow_points": [flow_point],
        "surface_cells": [],
        "level_dict": {
            "atm_iv_7d": 0.20,
            "atm_iv_30d": 0.21,
            "atm_iv_90d": 0.22,
            "rr25_30d": -0.01,
            "bf25_30d": 0.02,
            "front_end_dominance": 0.01,
        },
        "flow_dict": {
            "d_atm_iv_7d_1d": 0.01,
        },
        "level_pcts": {"atm_iv_7d": 60.0},
        "flow_pcts": {"d_atm_iv_7d_1d": 55.0},
        "state_score": 70.0,
        "stress_score": 25.0,
        "quadrant": "Compression",
    }


class TestDailyHistorySourceFactory(unittest.TestCase):
    def test_factory_uses_nse_udiff_setting_by_default(self):
        from phase0.history_sources import get_daily_history_source
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        source = get_daily_history_source(_make_settings(), None)
        self.assertIsInstance(source, NseUdiffDailyHistorySource)

    def test_factory_allows_upstox_override(self):
        from phase0.history_sources import get_daily_history_source
        from phase0.history_sources.upstox_daily import UpstoxDailyHistorySource

        source = get_daily_history_source(_make_settings(), "upstox")
        self.assertIsInstance(source, UpstoxDailyHistorySource)


class TestRunHistoryDailySelection(unittest.TestCase):
    def test_load_baselines_uses_target_day(self):
        from verify_pipeline import _load_baselines

        settings = _make_settings(supabase_db_url="postgresql://unused")
        with patch("worker.db.WorkerDatabase") as MockDB:
            db = MockDB.return_value.__enter__.return_value
            db.fetch_metric_baselines.return_value = {"atm_iv_7d": [0.2]}
            db.fetch_flow_baselines.return_value = {"d_atm_iv_7d_1d": [0.01]}

            baselines, flow_baselines = _load_baselines(settings, date(2026, 4, 2))

        self.assertEqual(baselines, {"atm_iv_7d": [0.2]})
        self.assertEqual(flow_baselines, {"d_atm_iv_7d_1d": [0.01]})
        db.fetch_metric_baselines.assert_called_once_with(date(2026, 4, 2), lookback_days=252)
        db.fetch_flow_baselines.assert_called_once_with(date(2026, 4, 2), lookback_days=252)

    def test_nse_udiff_path_does_not_call_upstox_provider(self):
        from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
        from verify_pipeline import run_history_daily

        close_ts = datetime(2026, 4, 2, 15, 29, tzinfo=IST)
        snapshot = DailyCloseSnapshot(
            source_name="nse_udiff",
            target_date=date(2026, 4, 2),
            close_ts=close_ts,
            option_rows=[{
                "expiry": date(2026, 4, 28),
                "strike": 22700.0,
                "option_type": "CE",
                "bid": None,
                "ask": None,
                "ltp": 100.0,
                "volume": 10,
                "oi": 20,
                "quote_quality": "ltp_fallback",
            }],
            future_price=22766.6,
            spot_price=22713.1,
            meta={},
        )
        source = MagicMock()
        source.name = "nse_udiff"
        source.build_close_snapshot.return_value = DailyBuildResult(
            status="completed",
            snapshot=snapshot,
            warnings=[],
            diagnostics={},
        )

        expiry_nodes = [
            ExpiryNode(
                ts=close_ts,
                expiry=date(2026, 4, 28),
                dte_days=26.0,
                forward=22766.6,
                atm_strike=22700.0,
                atm_iv=0.20,
                iv_25c=0.19,
                iv_25p=0.21,
                rr25=-0.02,
                bf25=0.001,
                source_count=10,
                quality_score=0.7,
                method_json={},
            )
        ]

        args = SimpleNamespace(date="2026-04-02", skip_db=True, source="nse_udiff")
        settings = _make_settings()

        with patch("verify_pipeline.get_daily_history_source", return_value=source), \
             patch("verify_pipeline.get_provider") as mock_get_provider, \
             patch("worker.calendar.is_trading_day", return_value=True), \
             patch("verify_pipeline.compute_expiry_nodes", return_value=expiry_nodes), \
             patch("verify_pipeline._run_pipeline_for_minute", return_value=_fake_pipeline_result(close_ts)):
            rc = run_history_daily(settings, args)

        self.assertEqual(rc, 0)
        mock_get_provider.assert_not_called()
        self.assertFalse(args._outcome.diagnostics["flow_anchor_available"])
        self.assertIsNone(args._outcome.diagnostics["flow_anchor_date"])
        self.assertIsNone(args._outcome.diagnostics["flow_anchor_gap_days"])

    def test_daily_mode_loads_prior_close_from_latest_stored_day(self):
        from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
        from verify_pipeline import run_history_daily

        close_ts = datetime(2026, 4, 2, 15, 29, tzinfo=IST)
        snapshot = DailyCloseSnapshot(
            source_name="nse_udiff",
            target_date=date(2026, 4, 2),
            close_ts=close_ts,
            option_rows=[{
                "expiry": date(2026, 4, 28),
                "strike": 22700.0,
                "option_type": "CE",
                "bid": None,
                "ask": None,
                "ltp": 100.0,
                "volume": 10,
                "oi": 20,
                "quote_quality": "ltp_fallback",
            }],
            future_price=22766.6,
            spot_price=22713.1,
            meta={"option_rows": 1},
        )
        source = MagicMock()
        source.name = "nse_udiff"
        source.build_close_snapshot.return_value = DailyBuildResult(
            status="completed",
            snapshot=snapshot,
            warnings=[],
            diagnostics={"option_rows": 1},
        )

        expiry_nodes = [
            ExpiryNode(
                ts=close_ts,
                expiry=date(2026, 4, 28),
                dte_days=26.0,
                forward=22766.6,
                atm_strike=22700.0,
                atm_iv=0.20,
                iv_25c=0.19,
                iv_25p=0.21,
                rr25=-0.02,
                bf25=0.001,
                source_count=10,
                quality_score=0.7,
                method_json={},
            )
        ]

        args = SimpleNamespace(date="2026-04-02", skip_db=False, source="nse_udiff")
        settings = _make_settings(supabase_db_url="postgresql://unused")
        captured = {}

        def fake_run_pipeline_for_minute(**kwargs):
            captured["prior_close"] = kwargs["prior_close"]
            return _fake_pipeline_result(close_ts)

        with patch("verify_pipeline.get_daily_history_source", return_value=source), \
             patch("verify_pipeline.compute_expiry_nodes", return_value=expiry_nodes), \
             patch("verify_pipeline._run_pipeline_for_minute", side_effect=fake_run_pipeline_for_minute), \
             patch("verify_pipeline._load_baselines", return_value=(None, None)), \
             patch("worker.db.WorkerDatabase") as MockDB:
            db = MockDB.return_value.__enter__.return_value
            db.fetch_latest_metric_values_before_day.return_value = (
                date(2026, 4, 1),
                {
                    "atm_iv_7d": 0.21,
                    "atm_iv_30d": 0.22,
                    "rr25_30d": -0.01,
                    "bf25_30d": 0.02,
                },
            )
            rc = run_history_daily(settings, args)

        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["prior_close"],
            {
                "atm_iv_7d": 0.21,
                "atm_iv_30d": 0.22,
                "rr25_30d": -0.01,
                "bf25_30d": 0.02,
                "front_end_dominance": None,
            },
        )
        self.assertEqual(args._outcome.diagnostics["flow_anchor_date"], "2026-04-01")
        self.assertEqual(args._outcome.diagnostics["flow_anchor_gap_days"], 1)
        self.assertTrue(args._outcome.diagnostics["flow_anchor_available"])
        db.upsert_surface_cells.assert_called_once()
        db.upsert_dashboard.assert_called_once()
        db.upsert_daily_brief.assert_called_once()

    def test_daily_db_persist_marks_score_rows_provisional_without_full_history(self):
        from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
        from verify_pipeline import run_history_daily

        close_ts = datetime(2026, 4, 2, 15, 29, tzinfo=IST)
        snapshot = DailyCloseSnapshot(
            source_name="nse_udiff",
            target_date=date(2026, 4, 2),
            close_ts=close_ts,
            option_rows=[{
                "expiry": date(2026, 4, 28),
                "strike": 22700.0,
                "option_type": "CE",
                "bid": None,
                "ask": None,
                "ltp": 100.0,
                "volume": 10,
                "oi": 20,
                "quote_quality": "ltp_fallback",
            }],
            future_price=22766.6,
            spot_price=22713.1,
            meta={},
        )
        source = MagicMock()
        source.name = "nse_udiff"
        source.build_close_snapshot.return_value = DailyBuildResult(
            status="completed",
            snapshot=snapshot,
            warnings=[],
            diagnostics={},
        )
        expiry_nodes = [
            ExpiryNode(
                ts=close_ts,
                expiry=date(2026, 4, 28),
                dte_days=26.0,
                forward=22766.6,
                atm_strike=22700.0,
                atm_iv=0.20,
                iv_25c=0.19,
                iv_25p=0.21,
                rr25=-0.02,
                bf25=0.001,
                source_count=10,
                quality_score=0.7,
                method_json={},
            )
        ]
        settings = _make_settings(supabase_db_url="postgresql://unused")
        args = SimpleNamespace(date="2026-04-02", skip_db=False, source="nse_udiff")

        with patch("verify_pipeline.get_daily_history_source", return_value=source), \
             patch("verify_pipeline.compute_expiry_nodes", return_value=expiry_nodes), \
             patch("verify_pipeline._run_pipeline_for_minute", return_value=_fake_pipeline_result_with_points(close_ts)), \
             patch("verify_pipeline._load_baselines", return_value=(
                 {"atm_iv_7d": [0.2] * 60},
                 {"d_atm_iv_7d_1d": [0.01] * 60},
             )), \
             patch("worker.db.WorkerDatabase") as MockDB:
            db = MockDB.return_value.__enter__.return_value
            db.fetch_latest_metric_values_before_day.return_value = (date(2026, 4, 1), {})
            rc = run_history_daily(settings, args)

        self.assertEqual(rc, 0)
        metric_rows = db.upsert_metric_series.call_args.args[0]
        provisional_by_key = {row["metric_key"]: row["provisional"] for row in metric_rows}
        self.assertTrue(provisional_by_key["state_score"])
        self.assertTrue(provisional_by_key["stress_score"])

    def test_daily_db_persist_marks_rows_non_provisional_when_history_is_warm(self):
        from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
        from verify_pipeline import run_history_daily

        close_ts = datetime(2026, 4, 2, 15, 29, tzinfo=IST)
        snapshot = DailyCloseSnapshot(
            source_name="nse_udiff",
            target_date=date(2026, 4, 2),
            close_ts=close_ts,
            option_rows=[{
                "expiry": date(2026, 4, 28),
                "strike": 22700.0,
                "option_type": "CE",
                "bid": None,
                "ask": None,
                "ltp": 100.0,
                "volume": 10,
                "oi": 20,
                "quote_quality": "ltp_fallback",
            }],
            future_price=22766.6,
            spot_price=22713.1,
            meta={},
        )
        source = MagicMock()
        source.name = "nse_udiff"
        source.build_close_snapshot.return_value = DailyBuildResult(
            status="completed",
            snapshot=snapshot,
            warnings=[],
            diagnostics={},
        )
        expiry_nodes = [
            ExpiryNode(
                ts=close_ts,
                expiry=date(2026, 4, 28),
                dte_days=26.0,
                forward=22766.6,
                atm_strike=22700.0,
                atm_iv=0.20,
                iv_25c=0.19,
                iv_25p=0.21,
                rr25=-0.02,
                bf25=0.001,
                source_count=10,
                quality_score=0.7,
                method_json={},
            )
        ]
        settings = _make_settings(supabase_db_url="postgresql://unused")
        args = SimpleNamespace(date="2026-04-02", skip_db=False, source="nse_udiff")

        with patch("verify_pipeline.get_daily_history_source", return_value=source), \
             patch("verify_pipeline.compute_expiry_nodes", return_value=expiry_nodes), \
             patch("verify_pipeline._run_pipeline_for_minute", return_value=_fake_pipeline_result_with_points(close_ts)), \
             patch("verify_pipeline._load_baselines", return_value=(
                 {
                     "atm_iv_7d": [0.2] * 60,
                     "atm_iv_30d": [0.2] * 60,
                     "rr25_30d": [0.2] * 60,
                     "bf25_30d": [0.2] * 60,
                     "front_end_dominance": [0.2] * 60,
                 },
                 {
                     "d_atm_iv_7d_1d": [0.01] * 60,
                     "d_rr25_30d_1d": [0.01] * 60,
                     "d_bf25_30d_1d": [0.01] * 60,
                     "d_front_end_dominance_1d": [0.01] * 60,
                 },
             )), \
             patch("worker.db.WorkerDatabase") as MockDB:
            db = MockDB.return_value.__enter__.return_value
            db.fetch_latest_metric_values_before_day.return_value = (date(2026, 4, 1), {})
            rc = run_history_daily(settings, args)

        self.assertEqual(rc, 0)
        metric_rows = db.upsert_metric_series.call_args.args[0]
        provisional_by_key = {row["metric_key"]: row["provisional"] for row in metric_rows}
        self.assertFalse(provisional_by_key["atm_iv_7d"])
        self.assertFalse(provisional_by_key["d_atm_iv_7d_1d"])
        self.assertFalse(provisional_by_key["state_score"])
        self.assertFalse(provisional_by_key["stress_score"])


if __name__ == "__main__":
    unittest.main()
