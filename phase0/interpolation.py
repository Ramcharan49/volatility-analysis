"""Constant-maturity interpolation via total-variance space.

Interpolates per-expiry ExpiryNodes to fixed-tenor ConstantMaturityNodes
(7D, 30D, 90D) using linear interpolation in total-variance (w = sigma^2 * T).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Optional, Sequence

from phase0.models import ConstantMaturityNode, ExpiryNode


DEFAULT_TENORS = [7, 30, 90]
MIN_DTE_FOR_INTERPOLATION = 0.5  # Exclude near-expiry nodes with unreliable IV


def interpolate_constant_maturity(
    expiry_nodes: List[ExpiryNode],
    target_tenors: Sequence[int] = DEFAULT_TENORS,
    min_quality_score: float = 0.4,
) -> List[ConstantMaturityNode]:
    """Interpolate per-expiry nodes to fixed tenors in total-variance space.

    Returns one ConstantMaturityNode per target tenor. Nodes with
    dte_days < MIN_DTE_FOR_INTERPOLATION or quality_score below the threshold
    are excluded.
    """
    base_filter = [
        node for node in expiry_nodes
        if node.dte_days >= MIN_DTE_FOR_INTERPOLATION and node.atm_iv is not None
    ]
    usable = [n for n in base_filter if n.quality_score >= min_quality_score]
    # Graceful fallback: if quality gate removes everything, relax threshold
    if not usable and base_filter:
        usable = [n for n in base_filter if n.quality_score >= min_quality_score / 2.0]
    usable.sort(key=lambda n: n.dte_days)

    if not usable:
        return []

    result: List[ConstantMaturityNode] = []
    for tenor_days in target_tenors:
        cm_node = _interpolate_single_tenor(usable, tenor_days)
        if cm_node is not None:
            result.append(cm_node)
    return result


def _interpolate_single_tenor(
    nodes: List[ExpiryNode],
    tenor_days: int,
) -> Optional[ConstantMaturityNode]:
    """Interpolate (or extrapolate) to a single target tenor."""
    if not nodes:
        return None

    target_dte = float(tenor_days)
    ts = nodes[0].ts  # All nodes share the same snapshot timestamp

    # Single expiry: flat extrapolation
    if len(nodes) == 1:
        node = nodes[0]
        return ConstantMaturityNode(
            ts=ts,
            tenor_code="%dd" % tenor_days,
            tenor_days=tenor_days,
            atm_iv=node.atm_iv,
            iv_25c=node.iv_25c,
            iv_25p=node.iv_25p,
            iv_10c=None,
            iv_10p=None,
            rr25=node.rr25,
            bf25=node.bf25,
            quality="single_expiry",
            bracket_expiries=[node.expiry],
        )

    # Find bracket
    left: Optional[ExpiryNode] = None
    right: Optional[ExpiryNode] = None
    for i in range(len(nodes) - 1):
        if nodes[i].dte_days <= target_dte <= nodes[i + 1].dte_days:
            left = nodes[i]
            right = nodes[i + 1]
            break

    if left is not None and right is not None:
        # Interpolate in total-variance space
        vol_fields = _interpolate_vol_fields(left, right, target_dte)
        rr25, bf25 = _recompute_rr_bf(vol_fields)
        return ConstantMaturityNode(
            ts=ts,
            tenor_code="%dd" % tenor_days,
            tenor_days=tenor_days,
            atm_iv=vol_fields.get("atm_iv"),
            iv_25c=vol_fields.get("iv_25c"),
            iv_25p=vol_fields.get("iv_25p"),
            iv_10c=None,
            iv_10p=None,
            rr25=rr25,
            bf25=bf25,
            quality="interpolated",
            bracket_expiries=[left.expiry, right.expiry],
        )

    # Extrapolate from nearest node
    nearest = min(nodes, key=lambda n: abs(n.dte_days - target_dte))
    return ConstantMaturityNode(
        ts=ts,
        tenor_code="%dd" % tenor_days,
        tenor_days=tenor_days,
        atm_iv=nearest.atm_iv,
        iv_25c=nearest.iv_25c,
        iv_25p=nearest.iv_25p,
        iv_10c=None,
        iv_10p=None,
        rr25=nearest.rr25,
        bf25=nearest.bf25,
        quality="extrapolated",
        bracket_expiries=[nearest.expiry],
    )


def _interpolate_vol_fields(
    left: ExpiryNode,
    right: ExpiryNode,
    target_dte: float,
) -> Dict[str, Optional[float]]:
    """Interpolate all vol fields in total-variance space."""
    result: Dict[str, Optional[float]] = {}
    for field_name in ("atm_iv", "iv_25c", "iv_25p"):
        left_iv = getattr(left, field_name)
        right_iv = getattr(right, field_name)
        result[field_name] = _total_variance_interp(
            left_iv, left.dte_days,
            right_iv, right.dte_days,
            target_dte,
        )
    return result


def _total_variance_interp(
    iv_left: Optional[float],
    dte_left: float,
    iv_right: Optional[float],
    dte_right: float,
    dte_target: float,
) -> Optional[float]:
    """Interpolate a single IV in total-variance (w = sigma^2 * T) space.

    w = iv^2 * (dte / 365)
    Linearly interpolate w, then convert back: iv = sqrt(w / T_target)
    Clamps to ensure monotonic total variance (no calendar arbitrage).
    """
    if iv_left is None or iv_right is None:
        return None

    t_left = dte_left / 365.0
    t_right = dte_right / 365.0
    t_target = dte_target / 365.0

    if t_right <= t_left or t_target <= 0:
        return iv_left

    w_left = iv_left * iv_left * t_left
    w_right = iv_right * iv_right * t_right

    # Linear interpolation weight
    alpha = (t_target - t_left) / (t_right - t_left)
    w_target = w_left + alpha * (w_right - w_left)

    # Clamp: total variance must be non-negative and monotonically increasing
    w_target = max(w_target, 0.0)

    if t_target <= 0:
        return None

    return math.sqrt(w_target / t_target)


def _recompute_rr_bf(
    vol_fields: Dict[str, Optional[float]],
) -> tuple:
    """Recompute RR25 and BF25 from interpolated vol fields."""
    iv_25c = vol_fields.get("iv_25c")
    iv_25p = vol_fields.get("iv_25p")
    atm_iv = vol_fields.get("atm_iv")

    rr25 = (iv_25c - iv_25p) if iv_25c is not None and iv_25p is not None else None
    bf25 = None
    if iv_25c is not None and iv_25p is not None and atm_iv is not None:
        bf25 = 0.5 * (iv_25c + iv_25p) - atm_iv

    return rr25, bf25
