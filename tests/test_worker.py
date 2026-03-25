from __future__ import annotations

import unittest
from datetime import datetime, time, timedelta

from phase0.config import Settings
from phase0.live import MinuteAccumulator
from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone
from worker.main import FlowRingBuffer, infer_phase, process_sealed_minute

IST = indian_timezone()


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        provider="upstox",
        upstox_api_key="test",
        upstox_api_secret="test",
        upstox_redirect_url="http://localhost",
        session_state_path="./state/session.json",
        artifacts_dir="./artifacts",
        risk_free_rate=0.06,
        phase0_symbol="NIFTY",
        spot_instrument_key="NSE_INDEX|Nifty 50",
        derivative_segment="NSE_FO",
        store_raw_json_in_db=False,
        expired_history_months=6,
        supabase_db_url=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestInferPhase(unittest.TestCase):
    def setUp(self):
        self.settings = _make_settings()

    def test_weekday_pre_market(self):
        # Monday 8:00 IST
        dt = datetime(2026, 3, 16, 8, 0, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "pre_market")

    def test_weekday_market_hours_open(self):
        dt = datetime(2026, 3, 16, 9, 15, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "market_hours")

    def test_weekday_market_hours_mid(self):
        dt = datetime(2026, 3, 16, 12, 0, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "market_hours")

    def test_weekday_market_close(self):
        dt = datetime(2026, 3, 16, 15, 30, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "market_hours")

    def test_weekday_post_market(self):
        dt = datetime(2026, 3, 16, 15, 45, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "post_market")

    def test_weekday_idle_evening(self):
        dt = datetime(2026, 3, 16, 17, 0, tzinfo=IST)
        self.assertEqual(infer_phase(dt, self.settings), "idle")

    def test_saturday_idle(self):
        dt = datetime(2026, 3, 21, 10, 0, tzinfo=IST)  # Saturday
        self.assertEqual(infer_phase(dt, self.settings), "idle")

    def test_sunday_idle(self):
        dt = datetime(2026, 3, 22, 10, 0, tzinfo=IST)  # Sunday
        self.assertEqual(infer_phase(dt, self.settings), "idle")


class TestFlowRingBuffer(unittest.TestCase):
    def test_empty_buffer_returns_empty_lagged(self):
        buf = FlowRingBuffer()
        result = buf.get_lagged(datetime(2026, 3, 16, 10, 0, tzinfo=IST))
        self.assertEqual(result, {})

    def test_append_and_retrieve_5m(self):
        buf = FlowRingBuffer()
        ts_base = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        # Add entries at t=0, t=5
        buf.append(ts_base, {"atm_iv_7d": 0.20})
        buf.append(ts_base + timedelta(minutes=5), {"atm_iv_7d": 0.22})

        lagged = buf.get_lagged(ts_base + timedelta(minutes=5))
        self.assertIn("5m", lagged)
        self.assertAlmostEqual(lagged["5m"]["atm_iv_7d"], 0.20)

    def test_prunes_old_entries(self):
        buf = FlowRingBuffer(max_minutes=10)
        ts_base = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        buf.append(ts_base, {"atm_iv_7d": 0.20})
        buf.append(ts_base + timedelta(minutes=15), {"atm_iv_7d": 0.22})
        # Old entry should be pruned
        self.assertEqual(len(buf._buffer), 1)

    def test_60m_lag(self):
        buf = FlowRingBuffer()
        ts_base = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        for i in range(65):
            buf.append(ts_base + timedelta(minutes=i), {"atm_iv_7d": 0.20 + i * 0.001})

        lagged = buf.get_lagged(ts_base + timedelta(minutes=64))
        self.assertIn("60m", lagged)
        # Value at minute 4 ≈ 0.204
        self.assertAlmostEqual(lagged["60m"]["atm_iv_7d"], 0.204, places=3)

    def test_no_match_beyond_tolerance(self):
        buf = FlowRingBuffer()
        ts_base = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        buf.append(ts_base, {"atm_iv_7d": 0.20})
        # 5m ago from minute 10 = minute 5, but closest entry is minute 0 (5 minutes away)
        # Tolerance is 90s, so 5 minutes away should not match
        lagged = buf.get_lagged(ts_base + timedelta(minutes=10))
        self.assertNotIn("5m", lagged)


class TestProcessSealedMinute(unittest.TestCase):
    def test_pipeline_without_db(self):
        """End-to-end: sealed minute → metrics, no DB."""
        from phase0.live import SealedMinuteResult
        from phase0.quant import black76_price

        ts = datetime(2026, 3, 16, 10, 0, tzinfo=IST)
        expiry = (ts + timedelta(days=30)).date()
        forward = 22000.0
        sigma = 0.20

        # Build expiry_node_rows (as dicts, mimicking what MinuteAccumulator produces)
        node = ExpiryNode(
            ts=ts, expiry=expiry, dte_days=30.0,
            forward=forward, atm_strike=22000.0, atm_iv=sigma,
            iv_25c=0.19, iv_25p=0.22,
            iv_10c=0.18, iv_10p=0.24,
            rr25=-0.03, bf25=0.005,
            source_count=50, quality_score=0.9,
            method_json={"pricing_model": "black_76"},
        )
        sealed = SealedMinuteResult(
            minute_ts=ts,
            underlying_rows=[],
            option_rows=[],
            expiry_node_rows=[
                {
                    "ts": node.ts, "expiry": node.expiry, "dte_days": node.dte_days,
                    "forward": node.forward, "atm_strike": node.atm_strike,
                    "atm_iv": node.atm_iv, "iv_25c": node.iv_25c, "iv_25p": node.iv_25p,
                    "iv_10c": node.iv_10c, "iv_10p": node.iv_10p,
                    "rr25": node.rr25, "bf25": node.bf25,
                    "source_count": node.source_count, "quality_score": node.quality_score,
                    "method_json": node.method_json,
                }
            ],
        )

        flow_buffer = FlowRingBuffer()
        prior_close = {}

        summary = process_sealed_minute(sealed, flow_buffer, prior_close, db=None)

        self.assertEqual(summary["expiry_nodes"], 1)
        self.assertGreater(summary["cm_nodes"], 0)
        self.assertEqual(summary["level_metrics"], 13)
        self.assertEqual(summary["flow_metrics"], 16)
        self.assertEqual(summary["surface_cells"], 15)


class TestMinuteAccumulatorMemoryBounds(unittest.TestCase):
    def test_prune_old_buckets(self):
        """Verify that feed_ticks prunes buckets older than 5 minutes."""
        from phase0.models import ProbeUniverseItem
        items = [
            ProbeUniverseItem(
                role="option", exchange="NSE", tradingsymbol="TEST",
                instrument_key="NSE_FO|TEST",
            )
        ]
        acc = MinuteAccumulator(items, rate=0.06)

        ts_base = datetime(2026, 3, 16, 10, 0, tzinfo=IST)

        # Manually add old buckets
        for i in range(10):
            minute_ts = ts_base + timedelta(minutes=i)
            acc.minute_buckets[minute_ts] = {"NSE_FO|TEST": {"payload": {}, "event_ts": minute_ts, "received_at": minute_ts}}

        self.assertEqual(len(acc.minute_buckets), 10)

        # Feed a tick at minute 10 — should prune buckets before minute 5
        acc.feed_ticks(
            [{"instrument_key": "NSE_FO|TEST", "last_price": 100}],
            ts_base + timedelta(minutes=10),
        )

        # Buckets 0-4 should be pruned (older than 5 minutes from minute 10)
        for ts in list(acc.minute_buckets.keys()):
            self.assertGreaterEqual(ts, ts_base + timedelta(minutes=5))


if __name__ == "__main__":
    unittest.main()
