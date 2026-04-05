"""Tests for V1 data-layer fixes (B1-B10).

Validates flow baseline key prefix, abs percentiles, stress semantics,
FLOW_BASE_METRICS expansion, post-market guard, score rows, gap_fill_log,
historical universe, backfill flow/scores, futures filter, and FlowRingBuffer extraction.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

from phase0.metrics import FLOW_BASE_METRICS, FLOW_METRIC_KEYS
from phase0.time_utils import indian_timezone
from worker.buffers import FlowRingBuffer
from worker.percentile import (
    compute_abs_flow_percentiles,
    compute_flow_percentiles,
    compute_state_score,
    compute_stress_score,
    empirical_percentile,
)

IST = indian_timezone()


# ── B1: Flow baseline key prefix ─────────────────────────────────────

class TestB1FlowBaselineKeyPrefix(unittest.TestCase):
    def test_fetch_flow_baselines_keys_have_d_prefix(self):
        """B1: SQL must produce keys like 'd_atm_iv_7d_1d', not 'atm_iv_7d_1d'."""
        # Verify via the SQL string in db.py source
        import inspect
        from worker.db import WorkerDatabase

        source = inspect.getsource(WorkerDatabase.fetch_flow_baselines)
        self.assertIn("'d_' || metric_key", source,
                       "fetch_flow_baselines SQL must prepend 'd_' prefix")


# ── B2: Absolute flow percentiles for stress ──────────────────────────

class TestB2AbsFlowPercentiles(unittest.TestCase):
    def test_abs_symmetry(self):
        """B2: abs(-0.03) and abs(+0.03) must produce the same percentile."""
        history = [-0.01, -0.005, 0.005, 0.01, 0.02, 0.015, -0.008, 0.012, -0.003, 0.007]
        flows_neg = {"d_atm_iv_7d_1d": -0.03}
        flows_pos = {"d_atm_iv_7d_1d": 0.03}
        baselines = {"d_atm_iv_7d_1d": history}

        pct_neg = compute_abs_flow_percentiles(flows_neg, baselines)
        pct_pos = compute_abs_flow_percentiles(flows_pos, baselines)

        self.assertEqual(pct_neg["d_atm_iv_7d_1d"], pct_pos["d_atm_iv_7d_1d"])

    def test_abs_vs_signed_differ(self):
        """B2: Signed and absolute percentiles should differ for negative values."""
        history = [-0.01, -0.005, 0.005, 0.01, 0.02, 0.015, -0.008, 0.012, -0.003, 0.007]
        flows = {"d_atm_iv_7d_1d": -0.03}
        baselines = {"d_atm_iv_7d_1d": history}

        signed_pct = compute_flow_percentiles(flows, baselines)
        abs_pct = compute_abs_flow_percentiles(flows, baselines)

        # Signed: -0.03 ranks very low. Absolute: 0.03 ranks very high.
        self.assertNotEqual(signed_pct["d_atm_iv_7d_1d"], abs_pct["d_atm_iv_7d_1d"])

    def test_stress_uses_abs_percentiles(self):
        """B2: worker/main.py must use compute_abs_flow_percentiles for stress."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        self.assertIn("compute_abs_flow_percentiles", source,
                       "worker/main.py must use compute_abs_flow_percentiles for stress")
        self.assertIn("compute_flow_percentiles", source)
        self.assertIn("compute_stress_score(flow_pcts, abs_flow_pcts)", source)

    def test_none_for_insufficient_history(self):
        """B2: Returns None when history is too short."""
        flows = {"d_atm_iv_7d_1d": 0.03}
        baselines = {"d_atm_iv_7d_1d": [0.01, 0.02]}  # Only 2, need 5
        result = compute_abs_flow_percentiles(flows, baselines)
        self.assertIsNone(result["d_atm_iv_7d_1d"])


# ── B3: FLOW_BASE_METRICS expansion ──────────────────────────────────

class TestB3FlowExpansion(unittest.TestCase):
    def test_atm_iv_30d_in_flow_base(self):
        """B3: FLOW_BASE_METRICS must include atm_iv_30d."""
        self.assertIn("atm_iv_30d", FLOW_BASE_METRICS)

    def test_flow_metrics_count_20(self):
        """B3: 5 bases x 4 windows = 20 flow metric keys."""
        self.assertEqual(len(FLOW_METRIC_KEYS), 20)

    def test_atm_30d_card_uses_correct_flow_key(self):
        """B3: ATM IV 30D card must use d_atm_iv_30d_1d, not d_atm_iv_7d_1d."""
        from worker.daily_brief import build_key_cards

        # The _CARD_DEFS are accessed via build_key_cards internals
        import inspect
        source = inspect.getsource(build_key_cards)
        self.assertIn('"d_atm_iv_30d_1d"', source,
                       "ATM IV 30D card must reference d_atm_iv_30d_1d")
        # Ensure the old wrong key is not used for 30D card
        lines = source.split("\n")
        for line in lines:
            if "ATM IV 30D" in line:
                self.assertNotIn("d_atm_iv_7d_1d", line,
                                  "ATM IV 30D card must not use d_atm_iv_7d_1d")


# ── B4: Post-market guard ─────────────────────────────────────────────

class TestB4PostMarketGuard(unittest.TestCase):
    def test_post_market_done_date_field_exists(self):
        """B4: Worker.__init__ must set _post_market_done_date."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        self.assertIn("_post_market_done_date", source)
        # Must be initialized in __init__
        init_section = source[source.index("def __init__"):source.index("def run(")]
        self.assertIn("_post_market_done_date", init_section)

    def test_post_market_guard_in_source(self):
        """B4: _run_post_market must check _post_market_done_date before running."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        pm_section = source[source.index("def _run_post_market"):]
        # Guard must be near the top of the method
        first_200_chars = pm_section[:500]
        self.assertIn("_post_market_done_date", first_200_chars)


# ── B5: Score rows in metric_series ────────────────────────────────────

class TestB5ScoreRows(unittest.TestCase):
    def test_scores_in_metric_series(self):
        """B5: process_sealed_minute must append state_score/stress_score rows."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        # Find the process_sealed_minute function
        psm_start = source.index("def process_sealed_minute")
        psm_section = source[psm_start:source.index("\nclass Worker")]
        self.assertIn('"state_score"', psm_section)
        self.assertIn('"stress_score"', psm_section)


# ── B6: gap_fill_log writes ───────────────────────────────────────────

class TestB6GapFillLog(unittest.TestCase):
    def test_insert_gap_fill_log_method_exists(self):
        """B6: WorkerDatabase must have insert_gap_fill_log."""
        from worker.db import WorkerDatabase
        self.assertTrue(hasattr(WorkerDatabase, "insert_gap_fill_log"))

    def test_update_gap_fill_log_method_exists(self):
        """B6: WorkerDatabase must have update_gap_fill_log."""
        from worker.db import WorkerDatabase
        self.assertTrue(hasattr(WorkerDatabase, "update_gap_fill_log"))

    def test_gap_fill_log_status_transitions(self):
        """B6: backfill_day must call gap_fill_log insert/update."""
        import inspect
        from worker.gap_fill import backfill_day

        source = inspect.getsource(backfill_day)
        self.assertIn("insert_gap_fill_log", source)
        self.assertIn("update_gap_fill_log", source)
        # Should handle completed, partial, unfillable statuses
        self.assertIn('"completed"', source)
        self.assertIn('"partial"', source)
        self.assertIn('"unfillable"', source)


# ── B7: Historical universe reconstruction ─────────────────────────────

class TestB7HistoricalUniverse(unittest.TestCase):
    def test_build_historical_universe_exists(self):
        """B7: build_historical_universe must be importable from worker.gap_fill."""
        from worker.gap_fill import build_historical_universe
        self.assertTrue(callable(build_historical_universe))

    def test_build_historical_universe_merges_sources(self):
        """B7: Must include spot, current instruments, and expired contracts."""
        import inspect
        from worker.gap_fill import build_historical_universe

        source = inspect.getsource(build_historical_universe)
        # Should fetch expired expiries
        self.assertIn("fetch_expired_expiries", source)
        # Should fetch expired option contracts
        self.assertIn("fetch_expired_option_contracts", source)
        # Should include spot
        self.assertIn("spot", source)

    def test_build_historical_universe_dte_anchor(self):
        """B7: DTE must be computed from gap_date, not today."""
        import inspect
        from worker.gap_fill import build_historical_universe

        source = inspect.getsource(build_historical_universe)
        # Should reference gap_date for DTE computation, not today
        self.assertIn("gap_date", source)
        # Should NOT use datetime.now for DTE
        self.assertNotIn("datetime.now(IST).date()" , source)

    def test_gap_fill_uses_historical_for_past(self):
        """B7: _run_gap_fill_with_db calls build_historical_universe for past-day gaps."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        gf_start = source.index("def _run_gap_fill_with_db")
        gf_section = source[gf_start:gf_start + 1500]
        self.assertIn("build_historical_universe", gf_section)


# ── B8: Flow metrics + scores + baselines in backfill ──────────────────

class TestB8BackfillFlow(unittest.TestCase):
    def test_backfill_includes_flow_metrics(self):
        """B8: _backfill_day_inner must compute and write flow metrics."""
        import inspect
        from worker.gap_fill import _backfill_day_inner

        source = inspect.getsource(_backfill_day_inner)
        self.assertIn("compute_flow_metrics", source)
        self.assertIn("FlowRingBuffer", source)

    def test_backfill_writes_baselines(self):
        """B8: Full-day backfill must write daily baselines."""
        import inspect
        from worker.gap_fill import _backfill_day_inner

        source = inspect.getsource(_backfill_day_inner)
        self.assertIn("upsert_metric_baselines", source)
        self.assertIn("upsert_flow_baselines", source)

    def test_backfill_writes_scores(self):
        """B8: Backfill must compute and write score rows."""
        import inspect
        from worker.gap_fill import _backfill_day_inner

        source = inspect.getsource(_backfill_day_inner)
        self.assertIn("state_score", source)
        self.assertIn("stress_score", source)
        self.assertIn("compute_state_score", source)
        self.assertIn("compute_stress_score", source)

    def test_backfill_day_accepts_baselines(self):
        """B8: backfill_day must accept baselines and flow_baselines params."""
        import inspect
        from worker.gap_fill import backfill_day

        sig = inspect.signature(backfill_day)
        self.assertIn("baselines", sig.parameters)
        self.assertIn("flow_baselines", sig.parameters)
        self.assertIn("prior_close", sig.parameters)


# ── B9: Futures filter ─────────────────────────────────────────────────

class TestB9FuturesFilter(unittest.TestCase):
    def test_backfill_futures_all_roles(self):
        """B9: Backfill must include future_next and future_far, not just future_front."""
        import inspect
        from worker.gap_fill import _backfill_day_inner

        source = inspect.getsource(_backfill_day_inner)
        # Should use startswith("future"), not == "future_front"
        self.assertIn('startswith("future")', source)
        self.assertNotIn('== "future_front"', source)


# ── B10: FlowRingBuffer extraction ─────────────────────────────────────

class TestB10FlowRingBufferExtraction(unittest.TestCase):
    def test_flow_ring_buffer_importable_from_buffers(self):
        """B10: FlowRingBuffer must be importable from worker.buffers."""
        from worker.buffers import FlowRingBuffer as FRB
        self.assertTrue(callable(FRB))

    def test_flow_ring_buffer_reexported_from_main(self):
        """B10: worker/main.py must import FlowRingBuffer from worker.buffers."""
        from pathlib import Path
        source = Path("worker/main.py").read_text()
        self.assertIn("from worker.buffers import FlowRingBuffer", source)

    def test_flow_ring_buffer_basic_functionality(self):
        """B10: FlowRingBuffer extracted version works correctly."""
        buf = FlowRingBuffer()
        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        buf.append(ts, {"atm_iv_7d": 0.20, "atm_iv_30d": 0.18})
        buf.append(ts + timedelta(minutes=5), {"atm_iv_7d": 0.22, "atm_iv_30d": 0.19})

        lagged = buf.get_lagged(ts + timedelta(minutes=5))
        self.assertIn("5m", lagged)
        self.assertAlmostEqual(lagged["5m"]["atm_iv_7d"], 0.20)


if __name__ == "__main__":
    unittest.main()
