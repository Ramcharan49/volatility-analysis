"""Tests for prompt rendering — ensures the LLM always sees:
  - A correctly formatted snapshot header
  - All configured grid + composite metrics, with [grid] / [composite-only] tags
  - The rr25_30d inversion annotation
  - A dated trail, with today's row marked
"""
from __future__ import annotations

import unittest
from datetime import date

from worker.narrative.context import (
    FlowEntry,
    MetricEntry,
    NarrativeContext,
    TrailPoint,
)
from worker.narrative.prompts import SYSTEM_PROMPT, build_user_prompt


def _ctx() -> NarrativeContext:
    return NarrativeContext(
        brief_date=date(2026, 4, 12),
        quadrant="Stress",
        state_score=57.3,
        stress_score=28.1,
        grid_metrics=[
            MetricEntry("atm_iv_7d", "ATM IV 7D", 0.22, 84.0, 84.0, "grid"),
            MetricEntry("atm_iv_30d", "ATM IV 30D", 0.20, 93.0, 93.0, "grid"),
            MetricEntry("term_7d_30d", "Term Spread 7D-30D", 0.01, 11.0, 11.0, "grid"),
            MetricEntry("rr25_30d", "Risk Reversal 30D", -0.05, 1.0, 99.0, "grid"),
        ],
        composite_metrics=[
            MetricEntry("bf25_30d", "Butterfly 30D", 0.009, 66.0, 66.0, "composite-only"),
            MetricEntry("front_end_dominance", "Front-End Dominance", 0.05, 54.0, 54.0, "composite-only"),
        ],
        flow_metrics=[
            FlowEntry("d_atm_iv_30d_1d", "Chg in 30D ATM IV", 0.001, 8.0),
            FlowEntry("d_rr25_30d_1d", "Chg in 30D Risk Reversal", -0.002, 31.0),
        ],
        trail=[
            TrailPoint(date(2026, 4, 10), 58.0, 22.7, "Stress"),
            TrailPoint(date(2026, 4, 11), 58.9, 25.4, "Stress"),
            TrailPoint(date(2026, 4, 12), 57.3, 28.1, "Stress"),
        ],
    )


class TestSystemPrompt(unittest.TestCase):
    def test_contains_core_constraints(self):
        # Spot-check the non-negotiable constraints in the system prompt.
        self.assertIn("no trading advice", SYSTEM_PROMPT.lower())
        self.assertIn("2-3 sentences", SYSTEM_PROMPT)
        self.assertIn("[grid]", SYSTEM_PROMPT)
        self.assertIn("[composite-only]", SYSTEM_PROMPT)
        self.assertIn("narrative", SYSTEM_PROMPT)  # JSON key


class TestUserPrompt(unittest.TestCase):
    def test_header_line(self):
        prompt = build_user_prompt(_ctx())
        self.assertIn("SNAPSHOT - 2026-04-12", prompt)
        self.assertIn("Quadrant:     Stress", prompt)
        self.assertIn("State score:  57.3", prompt)
        self.assertIn("Stress score: +28.1", prompt)

    def test_all_grid_metrics_surfaced(self):
        prompt = build_user_prompt(_ctx())
        for key in ("atm_iv_7d", "atm_iv_30d", "term_7d_30d", "rr25_30d"):
            self.assertIn(key, prompt)
            self.assertIn("[grid]", prompt)

    def test_composite_metrics_tagged_composite_only(self):
        prompt = build_user_prompt(_ctx())
        self.assertIn("bf25_30d", prompt)
        self.assertIn("front_end_dominance", prompt)
        self.assertIn("[composite-only]", prompt)

    def test_rr_inversion_annotation(self):
        prompt = build_user_prompt(_ctx())
        self.assertIn("inverted", prompt.lower())
        self.assertIn("extreme fear", prompt.lower())

    def test_flow_metrics_present_with_percentiles(self):
        prompt = build_user_prompt(_ctx())
        self.assertIn("d_atm_iv_30d_1d", prompt)
        self.assertIn("P8", prompt)
        self.assertIn("d_rr25_30d_1d", prompt)
        self.assertIn("P31", prompt)

    def test_trail_has_today_marker(self):
        prompt = build_user_prompt(_ctx())
        self.assertIn("Apr 12", prompt)
        self.assertIn("<- today", prompt)

    def test_null_percentiles_render_as_double_dash(self):
        ctx = NarrativeContext(
            brief_date=date(2026, 4, 12),
            quadrant=None,
            state_score=None,
            stress_score=None,
            grid_metrics=[
                MetricEntry("atm_iv_7d", "ATM IV 7D", None, None, None, "grid"),
            ],
        )
        prompt = build_user_prompt(ctx)
        self.assertIn("--", prompt)
        self.assertIn("Unknown", prompt)  # quadrant fallback


if __name__ == "__main__":
    unittest.main()
