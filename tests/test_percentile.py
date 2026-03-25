from __future__ import annotations

import unittest

from worker.percentile import (
    MIN_DAYS_FOR_PERCENTILE,
    classify_quadrant,
    compute_state_score,
    compute_stress_score,
    empirical_percentile,
    is_provisional,
)


class TestEmpiricalPercentile(unittest.TestCase):
    def test_median_value(self):
        history = list(range(1, 101))  # 1 to 100
        pct = empirical_percentile(50, history)
        # rank = 50, percentile = 50/101 * 100 ≈ 49.5
        self.assertAlmostEqual(pct, 50 / 101 * 100, places=2)

    def test_min_value(self):
        history = list(range(1, 101))
        pct = empirical_percentile(1, history)
        self.assertAlmostEqual(pct, 1 / 101 * 100, places=2)

    def test_max_value(self):
        history = list(range(1, 101))
        pct = empirical_percentile(100, history)
        self.assertAlmostEqual(pct, 100 / 101 * 100, places=2)

    def test_below_min_history(self):
        history = [1, 2, 3]  # Less than MIN_DAYS_FOR_PERCENTILE
        self.assertIsNone(empirical_percentile(2, history))

    def test_none_values_filtered(self):
        history = [None, 1, 2, None, 3, 4, 5]  # 5 non-None
        pct = empirical_percentile(3, history)
        self.assertIsNotNone(pct)

    def test_exact_min_history(self):
        history = list(range(MIN_DAYS_FOR_PERCENTILE))
        pct = empirical_percentile(2, history)
        self.assertIsNotNone(pct)


class TestIsProvisional(unittest.TestCase):
    def test_short_history(self):
        self.assertTrue(is_provisional(10))

    def test_long_history(self):
        self.assertFalse(is_provisional(100))

    def test_threshold(self):
        self.assertTrue(is_provisional(59))
        self.assertFalse(is_provisional(60))


class TestStateScore(unittest.TestCase):
    def test_all_at_50(self):
        pcts = {
            "atm_iv_7d": 50.0,
            "atm_iv_30d": 50.0,
            "front_end_dominance": 50.0,
            "rr25_30d": 50.0,  # inverted: 100 - 50 = 50
            "bf25_30d": 50.0,
        }
        score = compute_state_score(pcts)
        self.assertAlmostEqual(score, 50.0)

    def test_all_high(self):
        pcts = {
            "atm_iv_7d": 90.0,
            "atm_iv_30d": 90.0,
            "front_end_dominance": 90.0,
            "rr25_30d": 10.0,  # inverted: 100 - 10 = 90
            "bf25_30d": 90.0,
        }
        score = compute_state_score(pcts)
        self.assertAlmostEqual(score, 90.0)

    def test_missing_components_returns_none(self):
        pcts = {"atm_iv_7d": 50.0}  # Only 1 of 5
        score = compute_state_score(pcts)
        self.assertIsNone(score)

    def test_partial_components(self):
        pcts = {
            "atm_iv_7d": 50.0,
            "atm_iv_30d": 50.0,
            "front_end_dominance": 50.0,
        }
        score = compute_state_score(pcts)
        # 3 of 5 components present, rr25 and bf25 missing (None)
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 50.0)


class TestStressScore(unittest.TestCase):
    def test_all_at_50(self):
        pcts = {
            "d_atm_iv_7d_1d": 50.0,
            "d_rr25_30d_1d": 50.0,
            "d_bf25_30d_1d": 50.0,
            "d_front_end_dominance_1d": 50.0,
        }
        score = compute_stress_score(pcts)
        self.assertAlmostEqual(score, 50.0)

    def test_missing_returns_none(self):
        pcts = {"d_atm_iv_7d_1d": 50.0}  # Only 1 of 4
        score = compute_stress_score(pcts)
        self.assertIsNone(score)


class TestClassifyQuadrant(unittest.TestCase):
    def test_calm(self):
        self.assertEqual(classify_quadrant(30, 30), "Calm")

    def test_transition(self):
        self.assertEqual(classify_quadrant(30, 70), "Transition")

    def test_compression(self):
        self.assertEqual(classify_quadrant(70, 30), "Compression")

    def test_stress(self):
        self.assertEqual(classify_quadrant(70, 70), "Stress")

    def test_boundary_at_50(self):
        self.assertEqual(classify_quadrant(50, 50), "Stress")

    def test_none_returns_none(self):
        self.assertIsNone(classify_quadrant(None, 50))
        self.assertIsNone(classify_quadrant(50, None))

    def test_deterministic(self):
        """Same input always produces same output."""
        for _ in range(100):
            self.assertEqual(classify_quadrant(45.3, 67.8), "Transition")


if __name__ == "__main__":
    unittest.main()
