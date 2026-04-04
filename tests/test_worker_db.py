from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock

from worker.db import WorkerDatabase


class TestWorkerDatabase(unittest.TestCase):
    def test_fetch_metric_baselines_uses_target_day_window(self):
        db = WorkerDatabase("postgresql://unused")
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [("atm_iv_7d", 0.21)]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        db.conn = conn

        values = db.fetch_metric_baselines(date(2026, 4, 10), lookback_days=30)

        self.assertEqual(values["atm_iv_7d"], [0.21])
        cursor.execute.assert_called_once()
        _, params = cursor.execute.call_args.args
        self.assertEqual(params, (date(2026, 3, 11), date(2026, 4, 10)))

    def test_fetch_flow_baselines_uses_target_day_window(self):
        db = WorkerDatabase("postgresql://unused")
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [("d_atm_iv_7d_1d", 0.01)]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        db.conn = conn

        values = db.fetch_flow_baselines(date(2026, 4, 10), lookback_days=30)

        self.assertEqual(values["d_atm_iv_7d_1d"], [0.01])
        cursor.execute.assert_called_once()
        _, params = cursor.execute.call_args.args
        self.assertEqual(params, (date(2026, 3, 11), date(2026, 4, 10)))

    def test_fetch_latest_metric_values_before_day_returns_anchor_date_and_metrics(self):
        db = WorkerDatabase("postgresql://unused")
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (datetime(2026, 4, 1, 15, 29),)
        cursor.fetchall.return_value = [
            ("atm_iv_7d", 0.21),
            ("rr25_30d", -0.01),
        ]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        db.conn = conn

        anchor_day, values = db.fetch_latest_metric_values_before_day(date(2026, 4, 2))

        self.assertEqual(anchor_day, date(2026, 4, 1))
        self.assertEqual(values["atm_iv_7d"], 0.21)
        self.assertEqual(values["rr25_30d"], -0.01)


if __name__ == "__main__":
    unittest.main()
