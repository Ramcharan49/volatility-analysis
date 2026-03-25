from __future__ import annotations

import unittest
from datetime import date, datetime

from phase0.interpolation import (
    DEFAULT_TENORS,
    MIN_DTE_FOR_INTERPOLATION,
    interpolate_constant_maturity,
    _total_variance_interp,
)
from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone

IST = indian_timezone()
TS = datetime(2026, 3, 16, 10, 0, tzinfo=IST)


def _make_node(dte_days: float, atm_iv: float = 0.20, **kwargs) -> ExpiryNode:
    """Helper to build an ExpiryNode with sensible defaults."""
    defaults = dict(
        ts=TS,
        expiry=date(2026, 4, 15),
        dte_days=dte_days,
        forward=22000.0,
        atm_strike=22000.0,
        atm_iv=atm_iv,
        iv_25c=kwargs.get("iv_25c", atm_iv - 0.01),
        iv_25p=kwargs.get("iv_25p", atm_iv + 0.02),
        iv_10c=kwargs.get("iv_10c", atm_iv - 0.02),
        iv_10p=kwargs.get("iv_10p", atm_iv + 0.04),
        rr25=kwargs.get("rr25"),
        bf25=kwargs.get("bf25"),
        source_count=50,
        quality_score=0.9,
    )
    return ExpiryNode(**defaults)


class TestTotalVarianceInterp(unittest.TestCase):
    def test_midpoint_interpolation(self):
        """At the midpoint between two equal-vol nodes, IV should equal input."""
        result = _total_variance_interp(0.20, 10.0, 0.20, 50.0, 30.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.20, places=6)

    def test_none_input(self):
        self.assertIsNone(_total_variance_interp(None, 10.0, 0.20, 50.0, 30.0))
        self.assertIsNone(_total_variance_interp(0.20, 10.0, None, 50.0, 30.0))

    def test_monotonic_total_variance(self):
        """Total variance w=iv^2*T should increase from left to right."""
        iv = _total_variance_interp(0.25, 10.0, 0.20, 50.0, 30.0)
        self.assertIsNotNone(iv)
        # w_left = 0.25^2 * 10/365 = 0.001712
        # w_right = 0.20^2 * 50/365 = 0.005479
        # w_target at 30 should be between them
        w_left = 0.25**2 * 10.0 / 365.0
        w_right = 0.20**2 * 50.0 / 365.0
        w_target = iv**2 * 30.0 / 365.0
        self.assertGreaterEqual(w_target, w_left)
        self.assertLessEqual(w_target, w_right)

    def test_zero_dte_target(self):
        """Target at DTE=0 falls back to iv_left (degenerate guard)."""
        result = _total_variance_interp(0.20, 10.0, 0.20, 50.0, 0.0)
        self.assertAlmostEqual(result, 0.20, places=6)

    def test_same_dte_left_right(self):
        """If left.dte == right.dte, return left IV (degenerate)."""
        result = _total_variance_interp(0.25, 30.0, 0.20, 30.0, 30.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.25, places=6)


class TestInterpolateConstantMaturity(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(interpolate_constant_maturity([]), [])

    def test_single_expiry_flat_extrapolation(self):
        """With one usable expiry, all tenors get flat extrapolation."""
        nodes = [_make_node(dte_days=20.0, atm_iv=0.22)]
        result = interpolate_constant_maturity(nodes)
        self.assertEqual(len(result), 3)
        for cm in result:
            self.assertEqual(cm.atm_iv, 0.22)
            self.assertEqual(cm.quality, "single_expiry")

    def test_near_expiry_excluded(self):
        """Nodes with dte_days < MIN_DTE_FOR_INTERPOLATION are excluded."""
        nodes = [_make_node(dte_days=0.2, atm_iv=0.30)]
        result = interpolate_constant_maturity(nodes)
        self.assertEqual(result, [])

    def test_interpolated_quality_when_bracketed(self):
        """30D target bracketed by 14D and 45D nodes → quality='interpolated'."""
        nodes = [
            _make_node(dte_days=14.0, atm_iv=0.22),
            _make_node(dte_days=45.0, atm_iv=0.18),
        ]
        result = interpolate_constant_maturity(nodes, target_tenors=[30])
        self.assertEqual(len(result), 1)
        cm = result[0]
        self.assertEqual(cm.quality, "interpolated")
        self.assertEqual(cm.tenor_code, "30d")
        self.assertEqual(cm.tenor_days, 30)
        # IV should be between the two bracket nodes
        self.assertGreater(cm.atm_iv, 0.17)
        self.assertLess(cm.atm_iv, 0.23)

    def test_extrapolated_quality_when_outside(self):
        """90D target beyond all nodes → quality='extrapolated'."""
        nodes = [
            _make_node(dte_days=14.0, atm_iv=0.22),
            _make_node(dte_days=45.0, atm_iv=0.18),
        ]
        result = interpolate_constant_maturity(nodes, target_tenors=[90])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].quality, "extrapolated")
        # Uses nearest node (45D), so atm_iv = 0.18
        self.assertAlmostEqual(result[0].atm_iv, 0.18, places=6)

    def test_rr25_bf25_recomputed(self):
        """RR25 and BF25 recomputed from interpolated iv_25c/iv_25p/atm_iv."""
        nodes = [
            _make_node(dte_days=14.0, atm_iv=0.20, iv_25c=0.19, iv_25p=0.22),
            _make_node(dte_days=45.0, atm_iv=0.18, iv_25c=0.17, iv_25p=0.20),
        ]
        result = interpolate_constant_maturity(nodes, target_tenors=[30])
        cm = result[0]
        self.assertIsNotNone(cm.rr25)
        self.assertIsNotNone(cm.bf25)
        # RR25 = iv_25c - iv_25p (negative for typical put skew)
        self.assertAlmostEqual(cm.rr25, cm.iv_25c - cm.iv_25p, places=10)
        # BF25 = 0.5*(iv_25c + iv_25p) - atm_iv
        self.assertAlmostEqual(cm.bf25, 0.5 * (cm.iv_25c + cm.iv_25p) - cm.atm_iv, places=10)

    def test_bracket_expiries_populated(self):
        """bracket_expiries should list the expiry dates of bracket nodes."""
        n1 = _make_node(dte_days=14.0, atm_iv=0.22)
        n2 = _make_node(dte_days=45.0, atm_iv=0.18)
        result = interpolate_constant_maturity([n1, n2], target_tenors=[30])
        cm = result[0]
        self.assertEqual(len(cm.bracket_expiries), 2)

    def test_multiple_expiries_correct_bracketing(self):
        """With 5 expiries, 7D/30D/90D should each find correct brackets."""
        nodes = [
            _make_node(dte_days=3.0, atm_iv=0.28),
            _make_node(dte_days=10.0, atm_iv=0.24),
            _make_node(dte_days=24.0, atm_iv=0.21),
            _make_node(dte_days=52.0, atm_iv=0.19),
            _make_node(dte_days=110.0, atm_iv=0.17),
        ]
        result = interpolate_constant_maturity(nodes)
        self.assertEqual(len(result), 3)

        by_tenor = {cm.tenor_code: cm for cm in result}

        # 7D: bracketed by 3D and 10D → interpolated
        self.assertEqual(by_tenor["7d"].quality, "interpolated")

        # 30D: bracketed by 24D and 52D → interpolated
        self.assertEqual(by_tenor["30d"].quality, "interpolated")

        # 90D: bracketed by 52D and 110D → interpolated
        self.assertEqual(by_tenor["90d"].quality, "interpolated")

    def test_none_atm_iv_excluded(self):
        """Nodes with atm_iv=None are filtered out."""
        nodes = [
            _make_node(dte_days=20.0, atm_iv=0.20),
            ExpiryNode(
                ts=TS, expiry=date(2026, 5, 1), dte_days=50.0,
                forward=22000.0, atm_strike=22000.0, atm_iv=None,
                iv_25c=None, iv_25p=None,
            ),
        ]
        result = interpolate_constant_maturity(nodes, target_tenors=[30])
        # Only one usable node, so single_expiry quality
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].quality, "single_expiry")

    def test_tenor_codes(self):
        """Tenor codes should be formatted as '7d', '30d', '90d'."""
        nodes = [_make_node(dte_days=20.0)]
        result = interpolate_constant_maturity(nodes)
        codes = [cm.tenor_code for cm in result]
        self.assertEqual(codes, ["7d", "30d", "90d"])

    def test_custom_tenors(self):
        """Custom target tenors work correctly."""
        nodes = [
            _make_node(dte_days=5.0, atm_iv=0.25),
            _make_node(dte_days=60.0, atm_iv=0.18),
        ]
        result = interpolate_constant_maturity(nodes, target_tenors=[14, 45])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].tenor_days, 14)
        self.assertEqual(result[1].tenor_days, 45)


if __name__ == "__main__":
    unittest.main()
