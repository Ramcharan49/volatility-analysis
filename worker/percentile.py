"""Percentile engine and composite scores.

Computes empirical percentiles for level and flow metrics,
state/stress scores, and regime quadrant classification.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional


# Minimum days of baseline data for percentile computation
MIN_DAYS_FOR_PERCENTILE = 5
MIN_DAYS_FOR_RELIABLE = 60

STATE_SCORE_LEVEL_KEYS = (
    "atm_iv_7d",
    "atm_iv_30d",
    "front_end_dominance",
    "rr25_30d",
    "bf25_30d",
)

STRESS_SCORE_FLOW_KEYS = (
    "d_atm_iv_7d_1d",
    "d_rr25_30d_1d",
    "d_bf25_30d_1d",
    "d_front_end_dominance_1d",
)


def empirical_percentile(value: float, history: List[float]) -> Optional[float]:
    """Compute empirical percentile: rank / (N+1) * 100.

    Returns None if history has fewer than MIN_DAYS_FOR_PERCENTILE entries.
    """
    clean = [v for v in history if v is not None]
    if len(clean) < MIN_DAYS_FOR_PERCENTILE:
        return None
    rank = sum(1 for v in clean if v <= value)
    return rank / (len(clean) + 1) * 100


def is_provisional(history_length: int) -> bool:
    """Determine if percentile is provisional (insufficient history)."""
    return history_length < MIN_DAYS_FOR_RELIABLE


def metric_history_is_provisional(
    histories: Optional[Dict[str, List[float]]],
    metric_key: str,
) -> bool:
    """Determine whether a single metric's history is still in warm-up."""
    if histories is None:
        return True
    return len(histories.get(metric_key, [])) < MIN_DAYS_FOR_RELIABLE


def score_history_is_provisional(
    histories: Optional[Dict[str, List[float]]],
    required_keys: Iterable[str],
) -> bool:
    """Determine whether all score-driving histories are reliable yet."""
    if histories is None:
        return True
    return any(metric_history_is_provisional(histories, key) for key in required_keys)


# ── Level percentiles ────────────────────────────────────────────────

def compute_level_percentiles(
    current_levels: Dict[str, Optional[float]],
    baselines: Dict[str, List[float]],
) -> Dict[str, Optional[float]]:
    """Compute percentile for each level metric vs daily-close history.

    Args:
        current_levels: {metric_key: current_value}
        baselines: {metric_key: [daily_close_values]}

    Returns:
        {metric_key: percentile_or_None}
    """
    result: Dict[str, Optional[float]] = {}
    for key, value in current_levels.items():
        if value is None:
            result[key] = None
            continue
        history = baselines.get(key, [])
        result[key] = empirical_percentile(value, history)
    return result


# ── Flow percentiles ─────────────────────────────────────────────────

def compute_flow_percentiles(
    current_flows: Dict[str, Optional[float]],
    flow_baselines: Dict[str, List[float]],
) -> Dict[str, Optional[float]]:
    """Compute percentile for each flow metric vs historical changes.

    Args:
        current_flows: {flow_metric_key: current_change_value}
        flow_baselines: {flow_metric_key: [historical_change_values]}

    Returns:
        {flow_metric_key: percentile_or_None}
    """
    result: Dict[str, Optional[float]] = {}
    for key, value in current_flows.items():
        if value is None:
            result[key] = None
            continue
        history = flow_baselines.get(key, [])
        result[key] = empirical_percentile(value, history)
    return result


def compute_abs_flow_percentiles(
    current_flows: Dict[str, Optional[float]],
    flow_baselines: Dict[str, List[float]],
) -> Dict[str, Optional[float]]:
    """Percentile of |current_change| vs |historical_changes| for stress scoring.

    Takes absolute values of both current and historical before ranking,
    so a -3% move and +3% move produce the same percentile.
    """
    result: Dict[str, Optional[float]] = {}
    for key, value in current_flows.items():
        if value is None:
            result[key] = None
            continue
        history = flow_baselines.get(key, [])
        abs_history = [abs(v) for v in history if v is not None]
        if len(abs_history) < MIN_DAYS_FOR_PERCENTILE:
            result[key] = None
            continue
        result[key] = empirical_percentile(abs(value), abs_history)
    return result


# ── Composite scores ─────────────────────────────────────────────────

def compute_state_score(percentiles: Dict[str, Optional[float]]) -> Optional[float]:
    """State score = mean of percentiles for:
    atm_iv_7d, atm_iv_30d, front_end_dominance, -rr25_30d, bf25_30d.

    For -rr25_30d: use (100 - pct(rr25_30d)) to invert the sign.
    Returns None if any required percentile is None.
    """
    pct_atm_7d = percentiles.get("atm_iv_7d")
    pct_atm_30d = percentiles.get("atm_iv_30d")
    pct_fed = percentiles.get("front_end_dominance")
    pct_rr25 = percentiles.get("rr25_30d")
    pct_bf25 = percentiles.get("bf25_30d")

    values = [pct_atm_7d, pct_atm_30d, pct_fed]
    if pct_rr25 is not None:
        values.append(100.0 - pct_rr25)  # Invert: high -RR25 → high state
    else:
        values.append(None)
    values.append(pct_bf25)

    clean = [v for v in values if v is not None]
    if len(clean) < 3:  # Need at least 3 of 5 components
        return None
    return sum(clean) / len(clean)


def compute_stress_score(flow_percentiles: Dict[str, Optional[float]]) -> Optional[float]:
    """Stress score = mean of percentiles for absolute 1D changes in:
    atm_iv_7d, rr25_30d, bf25_30d, front_end_dominance.

    Uses percentile of |change|, so we need the absolute-value percentile.
    Returns None if any required percentile is None.
    """
    keys = [
        "d_atm_iv_7d_1d",
        "d_rr25_30d_1d",
        "d_bf25_30d_1d",
        "d_front_end_dominance_1d",
    ]
    values = [flow_percentiles.get(k) for k in keys]
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    return sum(clean) / len(clean)


# ── Regime quadrant ──────────────────────────────────────────────────

def classify_quadrant(
    state_score: Optional[float],
    stress_score: Optional[float],
) -> Optional[str]:
    """Classify regime quadrant.

    Calm:        state < 50, stress < 50
    Transition:  state < 50, stress >= 50
    Compression: state >= 50, stress < 50
    Stress:      state >= 50, stress >= 50
    """
    if state_score is None or stress_score is None:
        return None
    if state_score < 50:
        return "Transition" if stress_score >= 50 else "Calm"
    else:
        return "Stress" if stress_score >= 50 else "Compression"
