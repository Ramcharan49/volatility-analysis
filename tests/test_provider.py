from __future__ import annotations

import unittest
from datetime import datetime

from phase0.providers.base import classify_quote_quality, top_of_book
from phase0.providers.upstox.quotes import normalise_snapshot_payload
from phase0.models import ProbeUniverseItem
from phase0.time_utils import indian_timezone


IST = indian_timezone()


class ClassifyQuoteQualityTests(unittest.TestCase):
    def test_valid_mid_tight_spread(self):
        result = classify_quote_quality(bid=100.0, ask=101.0, ltp=100.5)
        self.assertEqual(result, "valid_mid")

    def test_wide_mid(self):
        result = classify_quote_quality(bid=100.0, ask=110.0, ltp=105.0)
        self.assertEqual(result, "wide_mid")

    def test_ltp_fallback_zero_bid(self):
        result = classify_quote_quality(bid=0, ask=0, ltp=100.0)
        self.assertEqual(result, "ltp_fallback")

    def test_ltp_fallback_none_bid(self):
        result = classify_quote_quality(bid=None, ask=None, ltp=100.0)
        self.assertEqual(result, "ltp_fallback")

    def test_invalid_all_none(self):
        result = classify_quote_quality(bid=None, ask=None, ltp=None)
        self.assertEqual(result, "invalid")

    def test_invalid_all_zero(self):
        result = classify_quote_quality(bid=0, ask=0, ltp=0)
        self.assertEqual(result, "invalid")


class TopOfBookTests(unittest.TestCase):
    def test_upstox_depth_format(self):
        depth = {
            "buy": [{"price": 100.0, "quantity": 50, "orders": 3}],
            "sell": [{"price": 101.0, "quantity": 30, "orders": 2}],
        }
        bid, bid_qty, ask, ask_qty = top_of_book(depth)
        self.assertEqual(bid, 100.0)
        self.assertEqual(bid_qty, 50)
        self.assertEqual(ask, 101.0)
        self.assertEqual(ask_qty, 30)

    def test_empty_depth(self):
        bid, bid_qty, ask, ask_qty = top_of_book({})
        self.assertIsNone(bid)
        self.assertIsNone(bid_qty)
        self.assertIsNone(ask)
        self.assertIsNone(ask_qty)


class NormaliseSnapshotPayloadTests(unittest.TestCase):
    def test_spot_normalisation(self):
        item = ProbeUniverseItem(
            role="spot",
            exchange="NSE",
            tradingsymbol="Nifty 50",
            instrument_key="NSE_INDEX|Nifty 50",
            provider="upstox",
        )
        payload = {
            "last_price": 22100.0,
            "volume": 0,
            "oi": 0,
            "depth": {
                "buy": [{"price": 22099.0, "quantity": 100, "orders": 5}],
                "sell": [{"price": 22101.0, "quantity": 80, "orders": 4}],
            },
        }
        ts = datetime(2026, 3, 19, 10, 0, tzinfo=IST)
        row_type, row = normalise_snapshot_payload(item, payload, ts)

        self.assertEqual(row_type, "underlying")
        self.assertEqual(row["source_type"], "index")
        self.assertEqual(row["last_price"], 22100.0)
        self.assertEqual(row["bid"], 22099.0)
        self.assertEqual(row["ask"], 22101.0)
        self.assertEqual(row["instrument_key"], "NSE_INDEX|Nifty 50")
        self.assertEqual(row["provider"], "upstox")

    def test_option_normalisation(self):
        item = ProbeUniverseItem(
            role="option",
            exchange="NFO",
            tradingsymbol="NIFTY2530622000CE",
            instrument_key="NSE_FO|54906",
            provider="upstox",
            instrument_type="CE",
            expiry=datetime(2026, 3, 6).date(),
            strike=22000.0,
            option_type="CE",
        )
        payload = {
            "last_price": 150.0,
            "volume": 5000,
            "oi": 10000,
            "last_trade_time": "2026-03-19T10:00:00+05:30",
            "depth": {
                "buy": [{"price": 149.0, "quantity": 200, "orders": 10}],
                "sell": [{"price": 151.0, "quantity": 180, "orders": 8}],
            },
        }
        ts = datetime(2026, 3, 19, 10, 0, tzinfo=IST)
        row_type, row = normalise_snapshot_payload(item, payload, ts)

        self.assertEqual(row_type, "option")
        self.assertEqual(row["strike"], 22000.0)
        self.assertEqual(row["option_type"], "CE")
        self.assertEqual(row["bid"], 149.0)
        self.assertEqual(row["ask"], 151.0)
        self.assertEqual(row["ltp"], 150.0)
        self.assertEqual(row["bid_qty"], 200)
        self.assertEqual(row["ask_qty"], 180)
        self.assertEqual(row["quote_quality"], "valid_mid")

    def test_future_normalisation(self):
        item = ProbeUniverseItem(
            role="future_front",
            exchange="NFO",
            tradingsymbol="NIFTY26MARFUT",
            instrument_key="NSE_FO|55000",
            provider="upstox",
            instrument_type="FUT",
        )
        payload = {
            "last_price": 22150.0,
            "volume": 50000,
            "oi": 100000,
            "depth": {
                "buy": [{"price": 22149.0, "quantity": 300, "orders": 15}],
                "sell": [{"price": 22151.0, "quantity": 250, "orders": 12}],
            },
        }
        ts = datetime(2026, 3, 19, 10, 0, tzinfo=IST)
        row_type, row = normalise_snapshot_payload(item, payload, ts)

        self.assertEqual(row_type, "underlying")
        self.assertEqual(row["source_type"], "future")
        self.assertEqual(row["last_price"], 22150.0)


class CandleParsingTests(unittest.TestCase):
    def test_parse_candles(self):
        from phase0.providers.upstox.history import _parse_candles

        response = {
            "data": {
                "candles": [
                    ["2026-03-18T00:00:00+05:30", 22000.0, 22100.0, 21900.0, 22050.0, 100000, 50000],
                    ["2026-03-17T00:00:00+05:30", 21900.0, 22000.0, 21800.0, 21950.0, 90000, 48000],
                ]
            }
        }
        candles = _parse_candles(response)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["open"], 22000.0)
        self.assertEqual(candles[0]["close"], 22050.0)
        self.assertEqual(candles[0]["volume"], 100000)
        self.assertEqual(candles[0]["oi"], 50000)

    def test_parse_candles_empty(self):
        from phase0.providers.upstox.history import _parse_candles

        self.assertEqual(_parse_candles({}), [])
        self.assertEqual(_parse_candles({"data": {}}), [])
        self.assertEqual(_parse_candles({"data": {"candles": []}}), [])


class InstrumentNormalisationTests(unittest.TestCase):
    def test_normalise_instrument_row(self):
        from phase0.providers.upstox.instruments import _normalize_instrument_row as _normalise_row

        raw = {
            "instrument_key": "NSE_FO|54906",
            "trading_symbol": "NIFTY2530622000CE",
            "segment": "NSE_FO",
            "instrument_type": "CE",
            "name": "NIFTY",
            "expiry": "2025-03-06",
            "strike_price": 22000.0,
            "lot_size": 50,
            "tick_size": 0.05,
            "exchange_token": 54906,
        }
        normalised = _normalise_row(raw)
        self.assertEqual(normalised["instrument_key"], "NSE_FO|54906")
        self.assertEqual(normalised["tradingsymbol"], "NIFTY2530622000CE")
        self.assertEqual(normalised["segment"], "NSE_FO")
        self.assertEqual(normalised["name"], "NIFTY")
        self.assertEqual(normalised["instrument_type"], "CE")
        self.assertEqual(normalised["strike"], 22000.0)
        self.assertEqual(normalised["lot_size"], 50)
        self.assertEqual(normalised["instrument_token"], 54906)


if __name__ == "__main__":
    unittest.main()
