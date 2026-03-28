"""Shared buffer structures for the worker pipeline.

Extracted to avoid circular imports between worker.main and worker.gap_fill.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

from phase0.metrics import FLOW_BASE_METRICS

if TYPE_CHECKING:
    from worker.db import WorkerDatabase

log = logging.getLogger("worker")


class FlowRingBuffer:
    """In-memory ring buffer for recent level metric values.

    Stores up to max_minutes of historical level snapshots for
    computing flow metrics (5m, 15m, 60m deltas). Canonical source
    is the DB; this is an accelerator only.
    """

    def __init__(self, max_minutes: int = 65):
        self.max_minutes = max_minutes
        self._buffer: List[Dict] = []  # [{ts, metrics: {key: val}}]

    def append(self, ts: datetime, metrics: Dict[str, Optional[float]]) -> None:
        self._buffer.append({"ts": ts, "metrics": dict(metrics)})
        cutoff = ts - timedelta(minutes=self.max_minutes)
        self._buffer = [e for e in self._buffer if e["ts"] >= cutoff]

    def get_lagged(self, current_ts: datetime) -> Dict[str, Dict[str, Optional[float]]]:
        """Return lagged values for each flow window."""
        windows = {"5m": 5, "15m": 15, "60m": 60}
        result: Dict[str, Dict[str, Optional[float]]] = {}
        for window_code, minutes in windows.items():
            target_ts = current_ts - timedelta(minutes=minutes)
            closest = self._find_closest(target_ts)
            if closest is not None:
                result[window_code] = closest["metrics"]
        return result

    def _find_closest(self, target_ts: datetime) -> Optional[Dict]:
        if not self._buffer:
            return None
        best = None
        best_delta = None
        for entry in self._buffer:
            delta = abs((entry["ts"] - target_ts).total_seconds())
            if delta <= 90 and (best_delta is None or delta < best_delta):
                best = entry
                best_delta = delta
        return best

    def seed_from_db(self, db: WorkerDatabase, ref_ts: datetime) -> None:
        """Seed ring buffer from DB on startup/restart."""
        keys = list(FLOW_BASE_METRICS)
        data = db.fetch_latest_metric_values(keys, self.max_minutes, ref_ts)
        # Reconstruct per-minute entries
        by_ts: Dict[datetime, Dict] = {}
        for key, rows in data.items():
            for row in rows:
                ts = row["ts"]
                entry = by_ts.setdefault(ts, {})
                entry[key] = float(row["value"]) if row["value"] is not None else None
        for ts in sorted(by_ts.keys()):
            self.append(ts, by_ts[ts])
        if self._buffer:
            log.info("Seeded flow ring buffer with %d entries", len(self._buffer))
