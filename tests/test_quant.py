from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from phase0.quant import black76_price, cleaned_option_price, compute_expiry_node, compute_expiry_nodes, implied_volatility
from phase0.time_utils import indian_timezone


IST = indian_timezone()


class QuantTests(unittest.TestCase):
    def test_implied_volatility_round_trip(self):
        forward = 22000.0
        strike = 22000.0
        rate = 0.06
        time_to_expiry = 30.0 / 365.0
        sigma = 0.18
        price = black76_price("CE", forward, strike, time_to_expiry, rate, sigma)
        recovered = implied_volatility("CE", price, forward, strike, time_to_expiry, rate)
        self.assertIsNotNone(recovered)
        self.assertAlmostEqual(recovered, sigma, places=4)

    def test_compute_expiry_node_for_flat_surface(self):
        snapshot_ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        expiry = (snapshot_ts + timedelta(days=30)).date()
        forward = 22000.0
        rate = 0.06
        sigma = 0.2
        strikes = [21000.0, 21500.0, 22000.0, 22500.0, 23000.0]

        option_rows = []
        for strike in strikes:
            for option_type in ("CE", "PE"):
                price = black76_price(option_type, forward, strike, 30.0 / 365.0, rate, sigma)
                option_rows.append(
                    {
                        "expiry": expiry,
                        "strike": strike,
                        "option_type": option_type,
                        "bid": round(price * 0.995, 4),
                        "ask": round(price * 1.005, 4),
                        "ltp": round(price, 4),
                        "volume": 1000,
                        "oi": 2000,
                        "quote_quality": "valid_mid",
                    }
                )

        node = compute_expiry_node(
            option_rows=option_rows,
            expiry=expiry,
            snapshot_ts=snapshot_ts,
            future_price=forward,
            spot_price=forward,
            rate=rate,
        )

        self.assertIsNotNone(node)
        self.assertAlmostEqual(node.forward, forward, delta=25.0)
        self.assertAlmostEqual(node.atm_iv, sigma, delta=0.02)
        self.assertAlmostEqual(node.rr25, 0.0, delta=0.03)
        self.assertAlmostEqual(node.bf25, 0.0, delta=0.03)
        expected_keys = {
            "pricing_model",
            "delta_convention",
            "target_delta",
            "forward_source",
            "forward_quality",
            "atm_quality",
            "rr_bf_quality",
            "used_ltp_fallback",
            "bracketed_25d",
            "bracketed_10d",
            "wing_10_quality",
            "stress_window",
        }
        self.assertEqual(set(node.method_json.keys()), expected_keys)
        self.assertEqual(node.method_json["pricing_model"], "black_76")
        self.assertEqual(node.method_json["delta_convention"], "forward")
        self.assertEqual(node.method_json["forward_source"], "parity")
        self.assertEqual(node.method_json["forward_quality"], "high")
        self.assertEqual(node.method_json["atm_quality"], "high")
        self.assertEqual(node.method_json["stress_window"], "1d")

    def test_cleaned_option_price_requires_explicit_ltp_fallback(self):
        row = {
            "bid": None,
            "ask": None,
            "ltp": 120.5,
            "quote_quality": "ltp_fallback",
        }
        self.assertIsNone(cleaned_option_price(row))
        self.assertEqual(cleaned_option_price(row, allow_ltp_fallback=True), 120.5)

    def test_cleaned_option_price_rejects_wide_mid(self):
        row = {
            "bid": 100.0,
            "ask": 120.0,
            "ltp": 110.0,
            "quote_quality": "wide_mid",
        }
        self.assertIsNone(cleaned_option_price(row))


    def test_ltp_fallback_produces_nodes(self):
        snapshot_ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        expiry = (snapshot_ts + timedelta(days=30)).date()
        forward = 22000.0
        rate = 0.06
        sigma = 0.2
        strikes = [21500.0, 22000.0, 22500.0]

        option_rows = []
        for strike in strikes:
            for option_type in ("CE", "PE"):
                price = black76_price(option_type, forward, strike, 30.0 / 365.0, rate, sigma)
                option_rows.append(
                    {
                        "expiry": expiry,
                        "strike": strike,
                        "option_type": option_type,
                        "bid": None,
                        "ask": None,
                        "ltp": round(price, 4),
                        "volume": 100,
                        "oi": 500,
                        "quote_quality": "ltp_fallback",
                    }
                )

        nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=snapshot_ts,
            future_price=forward,
            spot_price=forward,
            rate=rate,
            allow_ltp_fallback=True,
        )
        self.assertGreater(len(nodes), 0)
        node = nodes[0]
        self.assertIsNotNone(node.atm_iv)
        self.assertTrue(node.method_json.get("used_ltp_fallback"))
        self.assertGreater(node.quality_score, 0)
        self.assertLessEqual(node.quality_score, 0.7)

    def test_ltp_fallback_rejected_without_flag(self):
        snapshot_ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        expiry = (snapshot_ts + timedelta(days=30)).date()
        forward = 22000.0
        rate = 0.06
        sigma = 0.2

        option_rows = []
        for strike in [21500.0, 22000.0, 22500.0]:
            for option_type in ("CE", "PE"):
                price = black76_price(option_type, forward, strike, 30.0 / 365.0, rate, sigma)
                option_rows.append(
                    {
                        "expiry": expiry,
                        "strike": strike,
                        "option_type": option_type,
                        "bid": None,
                        "ask": None,
                        "ltp": round(price, 4),
                        "volume": 100,
                        "oi": 500,
                        "quote_quality": "ltp_fallback",
                    }
                )

        nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=snapshot_ts,
            future_price=forward,
            spot_price=forward,
            rate=rate,
            allow_ltp_fallback=False,
        )
        for node in nodes:
            self.assertIsNone(node.atm_iv)


if __name__ == "__main__":
    unittest.main()
