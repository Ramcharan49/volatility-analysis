from __future__ import annotations

import unittest
from datetime import datetime

from phase0.metrics import (
    DELTA_BUCKETS,
    FLOW_BASE_METRICS,
    FLOW_METRIC_KEYS,
    FLOW_WINDOWS,
    LEVEL_METRIC_KEYS,
    TENOR_CODES,
    compute_flow_metrics,
    compute_level_metrics,
    compute_surface_grid,
    level_metrics_to_dict,
)
from phase0.models import ConstantMaturityNode
from phase0.time_utils import indian_timezone

IST = indian_timezone()
TS = datetime(2026, 3, 16, 10, 0, tzinfo=IST)


def _make_cm(tenor_code: str, tenor_days: int, atm_iv: float,
             iv_25c: float = None, iv_25p: float = None,
             iv_10c: float = None, iv_10p: float = None,
             quality: str = "interpolated") -> ConstantMaturityNode:
    if iv_25c is None:
        iv_25c = atm_iv - 0.01
    if iv_25p is None:
        iv_25p = atm_iv + 0.02
    if iv_10c is None:
        iv_10c = atm_iv - 0.02
    if iv_10p is None:
        iv_10p = atm_iv + 0.04
    return ConstantMaturityNode(
        ts=TS, tenor_code=tenor_code, tenor_days=tenor_days,
        atm_iv=atm_iv, iv_25c=iv_25c, iv_25p=iv_25p,
        iv_10c=iv_10c, iv_10p=iv_10p,
        rr25=iv_25c - iv_25p,
        bf25=0.5 * (iv_25c + iv_25p) - atm_iv,
        quality=quality,
    )


class TestLevelMetrics(unittest.TestCase):
    def setUp(self):
        self.cm_nodes = [
            _make_cm("7d", 7, 0.22),
            _make_cm("30d", 30, 0.20),
            _make_cm("90d", 90, 0.18),
        ]

    def test_returns_13_metrics(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        self.assertEqual(len(points), 13)

    def test_all_keys_present(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        keys = {p.metric_key for p in points}
        self.assertEqual(keys, set(LEVEL_METRIC_KEYS))

    def test_atm_iv_values(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertAlmostEqual(by_key["atm_iv_7d"].value, 0.22)
        self.assertAlmostEqual(by_key["atm_iv_30d"].value, 0.20)
        self.assertAlmostEqual(by_key["atm_iv_90d"].value, 0.18)

    def test_term_spreads(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        # term = short - long
        self.assertAlmostEqual(by_key["term_7d_30d"].value, 0.02)
        self.assertAlmostEqual(by_key["term_30d_90d"].value, 0.02)
        self.assertAlmostEqual(by_key["term_7d_90d"].value, 0.04)

    def test_front_end_dominance_equals_term_7d_30d(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertEqual(by_key["front_end_dominance"].value, by_key["term_7d_30d"].value)

    def test_rr25_bf25(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        # rr25 = iv_25c - iv_25p = (atm-0.01) - (atm+0.02) = -0.03
        self.assertAlmostEqual(by_key["rr25_7d"].value, -0.03)
        # bf25 = 0.5*(iv_25c + iv_25p) - atm = 0.5*(atm-0.01 + atm+0.02) - atm = 0.005
        self.assertAlmostEqual(by_key["bf25_7d"].value, 0.005)

    def test_tenor_code_annotation(self):
        points = compute_level_metrics(self.cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertEqual(by_key["atm_iv_7d"].tenor_code, "7d")
        self.assertIsNone(by_key["term_7d_30d"].tenor_code)
        self.assertIsNone(by_key["front_end_dominance"].tenor_code)

    def test_missing_tenor_returns_none(self):
        """If a tenor is missing, its metrics should be None."""
        cm_nodes = [_make_cm("7d", 7, 0.22)]  # only 7d
        points = compute_level_metrics(cm_nodes, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertIsNone(by_key["atm_iv_30d"].value)
        self.assertIsNone(by_key["term_30d_90d"].value)
        # term_7d_30d should be None because 30d is missing
        self.assertIsNone(by_key["term_7d_30d"].value)

    def test_empty_nodes(self):
        points = compute_level_metrics([], TS)
        self.assertEqual(len(points), 13)
        for p in points:
            self.assertIsNone(p.value)


class TestFlowMetrics(unittest.TestCase):
    def test_returns_16_metrics(self):
        current = {"atm_iv_7d": 0.22, "rr25_30d": -0.03, "bf25_30d": 0.005, "front_end_dominance": 0.02}
        lagged = {
            "5m": {"atm_iv_7d": 0.21, "rr25_30d": -0.025, "bf25_30d": 0.004, "front_end_dominance": 0.018},
            "15m": {"atm_iv_7d": 0.20, "rr25_30d": -0.02, "bf25_30d": 0.003, "front_end_dominance": 0.015},
            "60m": {"atm_iv_7d": 0.19, "rr25_30d": -0.015, "bf25_30d": 0.002, "front_end_dominance": 0.01},
        }
        prior_close = {"atm_iv_7d": 0.18, "rr25_30d": -0.01, "bf25_30d": 0.001, "front_end_dominance": 0.005}
        points = compute_flow_metrics(current, lagged, prior_close, TS)
        self.assertEqual(len(points), 16)

    def test_all_flow_keys_present(self):
        current = {k: 0.1 for k in FLOW_BASE_METRICS}
        lagged = {w: {k: 0.09 for k in FLOW_BASE_METRICS} for w in ["5m", "15m", "60m"]}
        prior_close = {k: 0.08 for k in FLOW_BASE_METRICS}
        points = compute_flow_metrics(current, lagged, prior_close, TS)
        keys = {p.metric_key for p in points}
        self.assertEqual(keys, set(FLOW_METRIC_KEYS))

    def test_flow_values(self):
        current = {"atm_iv_7d": 0.22, "rr25_30d": -0.03, "bf25_30d": 0.005, "front_end_dominance": 0.02}
        lagged = {"5m": {"atm_iv_7d": 0.21, "rr25_30d": -0.03, "bf25_30d": 0.005, "front_end_dominance": 0.02}}
        prior_close = {"atm_iv_7d": 0.20, "rr25_30d": -0.03, "bf25_30d": 0.005, "front_end_dominance": 0.02}
        points = compute_flow_metrics(current, lagged, prior_close, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertAlmostEqual(by_key["d_atm_iv_7d_5m"].value, 0.01)
        self.assertAlmostEqual(by_key["d_atm_iv_7d_1d"].value, 0.02)
        self.assertAlmostEqual(by_key["d_rr25_30d_5m"].value, 0.0)

    def test_missing_lagged_returns_none(self):
        current = {"atm_iv_7d": 0.22, "rr25_30d": -0.03, "bf25_30d": 0.005, "front_end_dominance": 0.02}
        lagged = {}  # no lagged data yet
        prior_close = {}
        points = compute_flow_metrics(current, lagged, prior_close, TS)
        for p in points:
            self.assertIsNone(p.value)

    def test_window_code_annotation(self):
        current = {k: 0.1 for k in FLOW_BASE_METRICS}
        lagged = {w: {k: 0.09 for k in FLOW_BASE_METRICS} for w in ["5m", "15m", "60m"]}
        prior_close = {k: 0.08 for k in FLOW_BASE_METRICS}
        points = compute_flow_metrics(current, lagged, prior_close, TS)
        by_key = {p.metric_key: p for p in points}
        self.assertEqual(by_key["d_atm_iv_7d_5m"].window_code, "5m")
        self.assertEqual(by_key["d_atm_iv_7d_1d"].window_code, "1d")


class TestSurfaceGrid(unittest.TestCase):
    def setUp(self):
        self.cm_nodes = [
            _make_cm("7d", 7, 0.22),
            _make_cm("30d", 30, 0.20),
            _make_cm("90d", 90, 0.18),
        ]

    def test_returns_15_cells(self):
        cells = compute_surface_grid(self.cm_nodes, TS)
        self.assertEqual(len(cells), 15)

    def test_all_tenor_delta_combinations(self):
        cells = compute_surface_grid(self.cm_nodes, TS)
        combos = {(c.tenor_code, c.delta_bucket) for c in cells}
        expected = {(t, d) for t in TENOR_CODES for d in DELTA_BUCKETS}
        self.assertEqual(combos, expected)

    def test_atm_values(self):
        cells = compute_surface_grid(self.cm_nodes, TS)
        atm_cells = {c.tenor_code: c for c in cells if c.delta_bucket == "ATM"}
        self.assertAlmostEqual(atm_cells["7d"].iv, 0.22)
        self.assertAlmostEqual(atm_cells["30d"].iv, 0.20)
        self.assertAlmostEqual(atm_cells["90d"].iv, 0.18)

    def test_put_skew_ordering(self):
        """P10 > P25 > ATM (typical equity put skew)."""
        cells = compute_surface_grid(self.cm_nodes, TS)
        for tenor in TENOR_CODES:
            tenor_cells = {c.delta_bucket: c for c in cells if c.tenor_code == tenor}
            self.assertGreater(tenor_cells["P10"].iv, tenor_cells["P25"].iv)
            self.assertGreater(tenor_cells["P25"].iv, tenor_cells["ATM"].iv)

    def test_quality_score_interpolated(self):
        cells = compute_surface_grid(self.cm_nodes, TS)
        for c in cells:
            self.assertEqual(c.quality_score, 1.0)

    def test_quality_score_single_expiry(self):
        cm_nodes = [_make_cm("7d", 7, 0.22, quality="single_expiry")]
        cells = compute_surface_grid(cm_nodes, TS)
        for c in cells:
            if c.tenor_code == "7d":
                self.assertAlmostEqual(c.quality_score, 0.7)
            else:
                self.assertAlmostEqual(c.quality_score, 0.0)

    def test_missing_tenor_returns_none_iv(self):
        cm_nodes = [_make_cm("7d", 7, 0.22)]  # only 7d
        cells = compute_surface_grid(cm_nodes, TS)
        for c in cells:
            if c.tenor_code != "7d":
                self.assertIsNone(c.iv)
                self.assertEqual(c.quality_score, 0.0)


class TestLevelMetricsToDict(unittest.TestCase):
    def test_conversion(self):
        cm_nodes = [
            _make_cm("7d", 7, 0.22),
            _make_cm("30d", 30, 0.20),
            _make_cm("90d", 90, 0.18),
        ]
        points = compute_level_metrics(cm_nodes, TS)
        d = level_metrics_to_dict(points)
        self.assertEqual(len(d), 13)
        self.assertAlmostEqual(d["atm_iv_7d"], 0.22)


if __name__ == "__main__":
    unittest.main()
