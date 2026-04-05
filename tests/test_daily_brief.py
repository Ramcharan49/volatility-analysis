from __future__ import annotations

import unittest
from datetime import date, datetime

from phase0.time_utils import indian_timezone
from worker.daily_brief import (
    build_insight_bullets,
    build_key_cards,
    generate_daily_brief,
    generate_dashboard_payload,
)

IST = indian_timezone()
TS = datetime(2026, 3, 16, 15, 30, tzinfo=IST)


class TestKeyCards(unittest.TestCase):
    def setUp(self):
        self.levels = {
            "atm_iv_7d": 0.22, "atm_iv_30d": 0.20,
            "term_7d_30d": 0.02, "rr25_30d": -0.03, "bf25_30d": 0.005,
        }
        self.percentiles = {
            "atm_iv_7d": 75.0, "atm_iv_30d": 60.0,
            "term_7d_30d": 80.0, "rr25_30d": 30.0, "bf25_30d": 45.0,
        }
        self.flows = {
            "d_atm_iv_7d_1d": 0.005,
            "d_rr25_30d_1d": -0.002,
            "d_bf25_30d_1d": 0.0001,
            "d_front_end_dominance_1d": 0.003,
        }

    def test_returns_5_cards(self):
        cards = build_key_cards(self.levels, self.percentiles, self.flows)
        self.assertEqual(len(cards), 5)

    def test_card_structure(self):
        cards = build_key_cards(self.levels, self.percentiles, self.flows)
        for card in cards:
            self.assertIn("label", card)
            self.assertIn("metric_key", card)
            self.assertIn("value", card)
            self.assertIn("percentile", card)
            self.assertIn("direction", card)
            self.assertIn("interpretation", card)

    def test_vol_formatting(self):
        cards = build_key_cards(self.levels, self.percentiles, self.flows)
        atm_card = cards[0]
        self.assertEqual(atm_card["value"], "22.00%")

    def test_direction_detection(self):
        cards = build_key_cards(self.levels, self.percentiles, self.flows)
        atm_card = cards[0]
        self.assertEqual(atm_card["direction"], "up")

    def test_none_values_handled(self):
        cards = build_key_cards({}, {}, {})
        self.assertEqual(len(cards), 5)
        for card in cards:
            self.assertIsNone(card["raw_value"])
            self.assertIsNone(card["percentile"])


class TestInsightBullets(unittest.TestCase):
    def test_returns_bullets(self):
        levels = {"term_7d_30d": 0.02, "rr25_30d": -0.04}
        flows = {"d_atm_iv_7d_1d": 0.01}
        percentiles = {"atm_iv_7d": 50.0}
        bullets = build_insight_bullets(levels, flows, percentiles)
        self.assertGreater(len(bullets), 0)
        self.assertLessEqual(len(bullets), 5)

    def test_extreme_percentile_flagged(self):
        levels = {}
        flows = {}
        percentiles = {"atm_iv_7d": 95.0}
        bullets = build_insight_bullets(levels, flows, percentiles)
        extreme_bullets = [b for b in bullets if "extreme" in b.lower()]
        self.assertGreater(len(extreme_bullets), 0)

    def test_empty_inputs(self):
        bullets = build_insight_bullets({}, {}, {})
        self.assertIsInstance(bullets, list)


class TestDashboardPayload(unittest.TestCase):
    def test_calm_quadrant(self):
        payload = generate_dashboard_payload(
            ts=TS, state_score=30.0, stress_score=-30.0,
            levels={"atm_iv_7d": 0.18},
            percentiles={"atm_iv_7d": 30.0},
            flows={},
        )
        self.assertEqual(payload["quadrant"], "Calm")
        self.assertIsNotNone(payload["key_cards"])
        self.assertIsNotNone(payload["scenario_implications"])

    def test_null_scores(self):
        payload = generate_dashboard_payload(
            ts=TS, state_score=None, stress_score=None,
            levels={}, percentiles={}, flows={},
        )
        self.assertIsNone(payload["quadrant"])
        self.assertEqual(payload["scenario_implications"], [])


class TestDailyBrief(unittest.TestCase):
    def test_generates_brief(self):
        brief = generate_daily_brief(
            brief_date=date(2026, 3, 16),
            state_score=70.0, stress_score=70.0,
            levels={"atm_iv_7d": 0.25, "atm_iv_30d": 0.22, "rr25_30d": -0.04},
            percentiles={"atm_iv_7d": 85.0},
            flows={"d_atm_iv_7d_1d": 0.01},
        )
        self.assertEqual(brief["quadrant"], "Stress")
        self.assertIn("rapid changes", brief["headline"])
        self.assertGreater(len(brief["body_text"]), 0)
        self.assertEqual(brief["brief_date"], date(2026, 3, 16))

    def test_deterministic(self):
        """Same input always produces same headline and quadrant."""
        kwargs = dict(
            brief_date=date(2026, 3, 16),
            state_score=30.0, stress_score=70.0,
            levels={"atm_iv_7d": 0.18},
            percentiles={}, flows={},
        )
        b1 = generate_daily_brief(**kwargs)
        b2 = generate_daily_brief(**kwargs)
        self.assertEqual(b1["quadrant"], b2["quadrant"])
        self.assertEqual(b1["headline"], b2["headline"])

    def test_negative_stress_with_high_state_is_compression(self):
        brief = generate_daily_brief(
            brief_date=date(2026, 3, 16),
            state_score=70.0, stress_score=-25.0,
            levels={"atm_iv_7d": 0.25},
            percentiles={},
            flows={},
        )
        self.assertEqual(brief["quadrant"], "Compression")
        self.assertIn("stable", brief["headline"])


if __name__ == "__main__":
    unittest.main()
