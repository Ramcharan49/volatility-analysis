"""Tests for NarrativeContext construction.

Mocks the DB connection so no Supabase is required. Asserts:
  - dashboard row unpacking produces the right metric entries
  - stress-aligned inversion fires only on rr25_30d
  - missing data degrades to None without raising
  - trail is sorted by day with quadrant pulled from daily_brief_history
"""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock

from worker.narrative.context import (
    GRID_FLOW_KEYS,
    GRID_LEVEL_KEYS,
    MetricEntry,
    _stress_aligned,
    build_context,
    metric_label,
)


def _cursor(fetchone=None, fetchall=None):
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall if fetchall is not None else []
    return cur


def _conn_with_queries(responses):
    """Build a fake psycopg connection that returns a response per cursor.
    `responses` is a list of dicts with `fetchone`/`fetchall` keys consumed
    in the order SQL statements execute in build_context."""
    responses_iter = iter(responses)
    conn = MagicMock()

    def cursor_factory():
        response = next(responses_iter)
        return _cursor(
            fetchone=response.get("fetchone"),
            fetchall=response.get("fetchall"),
        )

    conn.cursor.side_effect = cursor_factory
    return conn


class TestStressAlignment(unittest.TestCase):
    def test_rr25_inverted(self):
        self.assertEqual(_stress_aligned("rr25_30d", 1.0), 99.0)
        self.assertEqual(_stress_aligned("rr25_30d", 99.0), 1.0)

    def test_other_metrics_unchanged(self):
        self.assertEqual(_stress_aligned("atm_iv_30d", 93.0), 93.0)
        self.assertEqual(_stress_aligned("bf25_30d", 66.0), 66.0)

    def test_null_passes_through(self):
        self.assertIsNone(_stress_aligned("rr25_30d", None))
        self.assertIsNone(_stress_aligned("atm_iv_30d", None))


class TestMetricLabel(unittest.TestCase):
    def test_known_keys(self):
        self.assertEqual(metric_label("atm_iv_30d"), "ATM IV 30D")
        self.assertEqual(metric_label("rr25_30d"), "Risk Reversal 30D")
        self.assertEqual(metric_label("d_atm_iv_30d_1d"), "Chg in 30D ATM IV")

    def test_unknown_key_falls_back(self):
        self.assertEqual(metric_label("unknown_key"), "unknown_key")


class TestBuildContextShape(unittest.TestCase):
    """Exercise the full build_context flow with mocked SQL responses.

    The order of queries in build_context is:
      1. dashboard_current SELECT
      2. latest level snapshot (for FED + bf25 if missing from cards)
      3. latest flow snapshot
      4. daily_brief_history quadrants
      5. metric_series_1m state/stress daily
    """

    def test_happy_path_assembles_all_metrics(self):
        dashboard_row = (
            "Stress",           # quadrant
            57.3,               # state_score
            28.1,               # stress_score
            [                   # key_cards_json
                {"metric_key": "atm_iv_7d", "raw_value": 0.22, "percentile": 84.0},
                {"metric_key": "atm_iv_30d", "raw_value": 0.20, "percentile": 93.0},
                {"metric_key": "term_7d_30d", "raw_value": 0.01, "percentile": 11.0},
                {"metric_key": "rr25_30d", "raw_value": -0.05, "percentile": 1.0},
                {"metric_key": "bf25_30d", "raw_value": 0.009, "percentile": 66.0},
            ],
        )

        responses = [
            {"fetchone": dashboard_row},
            # Latest level snapshot: FED only (bf25 came from cards)
            {"fetchall": [("front_end_dominance", 0.05, 54.0, None)]},
            # Latest flow snapshot
            {"fetchall": [
                ("d_atm_iv_30d_1d", 0.001, 8.0, None),
                ("d_rr25_30d_1d", -0.002, 31.0, None),
            ]},
            # Quadrants by day
            {"fetchall": [
                (date(2026, 4, 10), "Stress"),
                (date(2026, 4, 11), "Stress"),
                (date(2026, 4, 12), "Stress"),
            ]},
            # State/stress scores by day
            {"fetchall": [
                (date(2026, 4, 10), "state_score", 58.0),
                (date(2026, 4, 10), "stress_score", 22.7),
                (date(2026, 4, 11), "state_score", 58.9),
                (date(2026, 4, 11), "stress_score", 25.4),
                (date(2026, 4, 12), "state_score", 57.3),
                (date(2026, 4, 12), "stress_score", 28.1),
            ]},
        ]
        conn = _conn_with_queries(responses)

        ctx = build_context(conn, brief_date=date(2026, 4, 12), trail_days=7)

        # Top-level snapshot
        self.assertEqual(ctx.quadrant, "Stress")
        self.assertAlmostEqual(ctx.state_score, 57.3)
        self.assertAlmostEqual(ctx.stress_score, 28.1)

        # 4 grid-level metrics in the configured order
        grid_keys = [m.key for m in ctx.grid_metrics]
        self.assertEqual(grid_keys, list(GRID_LEVEL_KEYS))

        # rr25_30d must have inverted stress-aligned percentile
        rr = next(m for m in ctx.grid_metrics if m.key == "rr25_30d")
        self.assertEqual(rr.raw_percentile, 1.0)
        self.assertEqual(rr.stress_aligned_percentile, 99.0)

        # Non-inverted metric stays identical
        atm30 = next(m for m in ctx.grid_metrics if m.key == "atm_iv_30d")
        self.assertEqual(atm30.raw_percentile, atm30.stress_aligned_percentile)

        # Composite-only metrics populated
        composite_keys = [m.key for m in ctx.composite_metrics]
        self.assertIn("bf25_30d", composite_keys)
        self.assertIn("front_end_dominance", composite_keys)
        fed = next(m for m in ctx.composite_metrics if m.key == "front_end_dominance")
        self.assertEqual(fed.surface, "composite-only")
        self.assertEqual(fed.raw_percentile, 54.0)

        # Flow metrics populated from flow snapshot
        flow_keys = [f.key for f in ctx.flow_metrics]
        self.assertEqual(flow_keys, list(GRID_FLOW_KEYS))
        d_rr = next(f for f in ctx.flow_metrics if f.key == "d_rr25_30d_1d")
        self.assertEqual(d_rr.raw_percentile, 31.0)

        # Trail sorted ascending by day with quadrant + scores
        self.assertEqual(len(ctx.trail), 3)
        self.assertEqual(ctx.trail[0].day, date(2026, 4, 10))
        self.assertEqual(ctx.trail[-1].day, date(2026, 4, 12))
        self.assertEqual(ctx.trail[-1].quadrant, "Stress")
        self.assertAlmostEqual(ctx.trail[-1].state_score, 57.3)

    def test_empty_dashboard_yields_null_snapshot(self):
        responses = [
            {"fetchone": None},  # no dashboard row
            {"fetchall": []},
            {"fetchall": []},
            {"fetchall": []},
            {"fetchall": []},
        ]
        conn = _conn_with_queries(responses)
        ctx = build_context(conn, brief_date=date(2026, 4, 12))

        self.assertIsNone(ctx.quadrant)
        self.assertIsNone(ctx.state_score)
        self.assertEqual(len(ctx.grid_metrics), 4)  # still emits 4 rows, all nullable
        for m in ctx.grid_metrics:
            self.assertIsNone(m.raw_percentile)
            self.assertIsNone(m.stress_aligned_percentile)


if __name__ == "__main__":
    unittest.main()
