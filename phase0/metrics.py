"""Level metrics, flow metrics, and surface grid computation.

Produces the 31 metric keys for metric_series_1m and the 15-cell surface grid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from phase0.models import ConstantMaturityNode


# ── Metric key constants ──────────────────────────────────────────────

TENOR_CODES = ["7d", "30d", "90d"]

LEVEL_METRIC_KEYS = [
    "atm_iv_7d", "atm_iv_30d", "atm_iv_90d",
    "rr25_7d", "rr25_30d", "rr25_90d",
    "bf25_7d", "bf25_30d", "bf25_90d",
    "term_7d_30d", "term_30d_90d", "term_7d_90d",
    "front_end_dominance",
]

FLOW_BASE_METRICS = ["atm_iv_7d", "atm_iv_30d", "rr25_30d", "bf25_30d", "front_end_dominance"]
FLOW_WINDOWS = ["5m", "15m", "60m", "1d"]
FLOW_WINDOW_MINUTES = {"5m": 5, "15m": 15, "60m": 60, "1d": None}

FLOW_METRIC_KEYS = [
    "d_%s_%s" % (base, window)
    for base in FLOW_BASE_METRICS
    for window in FLOW_WINDOWS
]

DELTA_BUCKETS = ["P25", "ATM", "C25"]


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class MetricPoint:
    ts: datetime
    metric_key: str
    tenor_code: Optional[str]
    window_code: Optional[str]
    value: Optional[float]


@dataclass
class SurfaceCell:
    tenor_code: str
    delta_bucket: str
    iv: Optional[float]
    quality_score: float = 0.0


# ── Level metrics ────────────────────────────────────────────────────

def compute_level_metrics(
    cm_nodes: List[ConstantMaturityNode],
    ts: datetime,
) -> List[MetricPoint]:
    """Compute 13 level metric points from constant-maturity nodes."""
    by_tenor: Dict[str, ConstantMaturityNode] = {}
    for node in cm_nodes:
        by_tenor[node.tenor_code] = node

    points: List[MetricPoint] = []

    # Per-tenor metrics: atm_iv, rr25, bf25
    for tenor in TENOR_CODES:
        node = by_tenor.get(tenor)
        points.append(MetricPoint(
            ts=ts, metric_key="atm_iv_%s" % tenor,
            tenor_code=tenor, window_code=None,
            value=node.atm_iv if node else None,
        ))
        points.append(MetricPoint(
            ts=ts, metric_key="rr25_%s" % tenor,
            tenor_code=tenor, window_code=None,
            value=node.rr25 if node else None,
        ))
        points.append(MetricPoint(
            ts=ts, metric_key="bf25_%s" % tenor,
            tenor_code=tenor, window_code=None,
            value=node.bf25 if node else None,
        ))

    # Term spreads: ATM_IV_short - ATM_IV_long
    atm_7d = by_tenor["7d"].atm_iv if "7d" in by_tenor else None
    atm_30d = by_tenor["30d"].atm_iv if "30d" in by_tenor else None
    atm_90d = by_tenor["90d"].atm_iv if "90d" in by_tenor else None

    term_7_30 = _safe_sub(atm_7d, atm_30d)
    term_30_90 = _safe_sub(atm_30d, atm_90d)
    term_7_90 = _safe_sub(atm_7d, atm_90d)

    points.append(MetricPoint(ts=ts, metric_key="term_7d_30d", tenor_code=None, window_code=None, value=term_7_30))
    points.append(MetricPoint(ts=ts, metric_key="term_30d_90d", tenor_code=None, window_code=None, value=term_30_90))
    points.append(MetricPoint(ts=ts, metric_key="term_7d_90d", tenor_code=None, window_code=None, value=term_7_90))

    # Front-end dominance = term_7d_30d (alias)
    points.append(MetricPoint(ts=ts, metric_key="front_end_dominance", tenor_code=None, window_code=None, value=term_7_30))

    return points


# ── Flow metrics ─────────────────────────────────────────────────────

def compute_flow_metrics(
    current_levels: Dict[str, Optional[float]],
    lagged_levels: Dict[str, Dict[str, Optional[float]]],
    prior_close: Dict[str, Optional[float]],
    ts: datetime,
) -> List[MetricPoint]:
    """Compute 16 flow metric points.

    Args:
        current_levels: {metric_key: current_value} for the 4 flow base metrics
        lagged_levels: {window_code: {metric_key: lagged_value}} for 5m/15m/60m
        prior_close: {metric_key: prior_day_close_value} for 1d window
        ts: snapshot timestamp
    """
    points: List[MetricPoint] = []
    for base_key in FLOW_BASE_METRICS:
        current = current_levels.get(base_key)
        for window in FLOW_WINDOWS:
            metric_key = "d_%s_%s" % (base_key, window)
            if window == "1d":
                lagged = prior_close.get(base_key)
            else:
                window_lags = lagged_levels.get(window, {})
                lagged = window_lags.get(base_key)
            value = _safe_sub(current, lagged)
            points.append(MetricPoint(
                ts=ts, metric_key=metric_key,
                tenor_code=None, window_code=window,
                value=value,
            ))
    return points


# ── Surface grid ─────────────────────────────────────────────────────

def compute_surface_grid(
    cm_nodes: List[ConstantMaturityNode],
    ts: datetime,
) -> List[SurfaceCell]:
    """Compute the 3x3 surface grid from constant-maturity nodes.

    Delta buckets: P25, ATM, C25
    Tenors: 7d, 30d, 90d
    """
    by_tenor: Dict[str, ConstantMaturityNode] = {}
    for node in cm_nodes:
        by_tenor[node.tenor_code] = node

    _field_map = {
        "P25": "iv_25p",
        "ATM": "atm_iv",
        "C25": "iv_25c",
    }

    cells: List[SurfaceCell] = []
    for tenor in TENOR_CODES:
        node = by_tenor.get(tenor)
        for bucket in DELTA_BUCKETS:
            iv = None
            quality = 0.0
            if node is not None:
                iv = getattr(node, _field_map[bucket], None)
                quality = 1.0 if node.quality == "interpolated" else (
                    0.7 if node.quality == "single_expiry" else 0.5
                )
            cells.append(SurfaceCell(
                tenor_code=tenor,
                delta_bucket=bucket,
                iv=iv,
                quality_score=quality if iv is not None else 0.0,
            ))
    return cells


# ── Helpers ──────────────────────────────────────────────────────────

def level_metrics_to_dict(points: List[MetricPoint]) -> Dict[str, Optional[float]]:
    """Convert list of MetricPoint to {metric_key: value} dict."""
    return {p.metric_key: p.value for p in points}


def _safe_sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b
