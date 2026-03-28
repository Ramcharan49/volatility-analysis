"""Deterministic daily brief generation.

Produces dashboard content (key cards, insights, implications) and
end-of-day brief text. No LLM — purely rule-based.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from worker.percentile import classify_quadrant


# ── Templates ────────────────────────────────────────────────────────

_QUADRANT_HEADLINES = {
    "Calm": "NIFTY vol surface is quiet — low levels, low motion",
    "Transition": "Volatility is moving fast despite low absolute levels",
    "Compression": "Elevated vol levels but market is stable — watching for resolution",
    "Stress": "High vol with rapid changes — active risk regime",
}

_QUADRANT_IMPLICATIONS = {
    "Calm": [
        "Option premiums are cheap relative to history",
        "Carry strategies may benefit from stable conditions",
    ],
    "Transition": [
        "Rapid vol changes may signal emerging directional move",
        "Short gamma positions face elevated repricing risk",
    ],
    "Compression": [
        "Elevated premiums persist despite calm price action",
        "Term structure shape may indicate hedging demand",
    ],
    "Stress": [
        "Broad repricing across the surface — hedging costs elevated",
        "Skew moves suggest directional positioning shifts",
    ],
}


# ── Key cards ────────────────────────────────────────────────────────

def build_key_cards(
    levels: Dict[str, Optional[float]],
    percentiles: Dict[str, Optional[float]],
    flows: Dict[str, Optional[float]],
) -> List[Dict]:
    """Build 5-6 key metric cards for dashboard display."""
    cards = []

    _CARD_DEFS = [
        ("ATM IV 7D", "atm_iv_7d", "d_atm_iv_7d_1d", "vol"),
        ("ATM IV 30D", "atm_iv_30d", "d_atm_iv_30d_1d", "vol"),
        ("Term Spread 7-30D", "term_7d_30d", "d_front_end_dominance_1d", "spread"),
        ("Risk Reversal 30D", "rr25_30d", "d_rr25_30d_1d", "skew"),
        ("Butterfly 30D", "bf25_30d", "d_bf25_30d_1d", "convexity"),
    ]

    for label, level_key, flow_key, category in _CARD_DEFS:
        value = levels.get(level_key)
        pct = percentiles.get(level_key)
        change = flows.get(flow_key)

        direction = "flat"
        if change is not None:
            if change > 0.001:
                direction = "up"
            elif change < -0.001:
                direction = "down"

        interpretation = _interpret_card(level_key, pct)

        cards.append({
            "label": label,
            "metric_key": level_key,
            "category": category,
            "value": _fmt_vol(value),
            "raw_value": value,
            "percentile": round(pct, 1) if pct is not None else None,
            "direction": direction,
            "interpretation": interpretation,
        })

    return cards


def _interpret_card(metric_key: str, pct: Optional[float]) -> str:
    if pct is None:
        return "Insufficient history for percentile context"
    if pct >= 90:
        return "Extremely elevated relative to history"
    if pct >= 75:
        return "Above average — elevated"
    if pct >= 25:
        return "Within normal range"
    if pct >= 10:
        return "Below average — subdued"
    return "Extremely low relative to history"


def _fmt_vol(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return "%.2f%%" % (value * 100)


# ── Insight bullets ──────────────────────────────────────────────────

def build_insight_bullets(
    levels: Dict[str, Optional[float]],
    flows: Dict[str, Optional[float]],
    percentiles: Dict[str, Optional[float]],
) -> List[str]:
    """Generate 3-5 insight bullets from current metrics."""
    bullets = []

    # Largest flow change
    flow_keys = ["d_atm_iv_7d_1d", "d_rr25_30d_1d", "d_bf25_30d_1d", "d_front_end_dominance_1d"]
    largest_flow = _largest_abs_flow(flows, flow_keys)
    if largest_flow:
        key, val = largest_flow
        direction = "rose" if val > 0 else "fell"
        name = _metric_label(key)
        bullets.append("%s %s by %.2f%% today" % (name, direction, abs(val) * 100))

    # Term structure shape
    term_7_30 = levels.get("term_7d_30d")
    if term_7_30 is not None:
        if term_7_30 > 0.01:
            bullets.append("Short-term vol above long-term (backwardation) — near-term uncertainty")
        elif term_7_30 < -0.01:
            bullets.append("Long-term vol above short-term (contango) — market pricing future risk")
        else:
            bullets.append("Flat term structure — no strong tenor signal")

    # Skew direction
    rr25 = levels.get("rr25_30d")
    if rr25 is not None:
        if rr25 < -0.03:
            bullets.append("Strong put skew at 30D — downside protection is expensive")
        elif rr25 > 0.01:
            bullets.append("Positive skew at 30D — unusual call-side premium")
        else:
            bullets.append("Moderate skew — balanced put/call pricing")

    # Extreme percentile flags
    for key in ["atm_iv_7d", "atm_iv_30d", "rr25_30d"]:
        pct = percentiles.get(key)
        if pct is not None:
            if pct > 90:
                bullets.append("%s is at the %dth percentile — historically extreme high" % (_metric_label(key), int(pct)))
            elif pct < 10:
                bullets.append("%s is at the %dth percentile — historically extreme low" % (_metric_label(key), int(pct)))

    return bullets[:5]


def _largest_abs_flow(flows: Dict[str, Optional[float]], keys: List[str]):
    best = None
    for key in keys:
        val = flows.get(key)
        if val is not None:
            if best is None or abs(val) > abs(best[1]):
                best = (key, val)
    return best


def _metric_label(key: str) -> str:
    labels = {
        "atm_iv_7d": "ATM IV 7D",
        "atm_iv_30d": "ATM IV 30D",
        "atm_iv_90d": "ATM IV 90D",
        "rr25_30d": "Risk Reversal 30D",
        "bf25_30d": "Butterfly 30D",
        "term_7d_30d": "Term Spread 7-30D",
        "front_end_dominance": "Front-End Dominance",
        "d_atm_iv_7d_1d": "ATM IV 7D",
        "d_rr25_30d_1d": "Risk Reversal 30D",
        "d_bf25_30d_1d": "Butterfly 30D",
        "d_front_end_dominance_1d": "Front-End Dominance",
    }
    return labels.get(key, key)


# ── Full brief ───────────────────────────────────────────────────────

def generate_dashboard_payload(
    ts: datetime,
    state_score: Optional[float],
    stress_score: Optional[float],
    levels: Dict[str, Optional[float]],
    percentiles: Dict[str, Optional[float]],
    flows: Dict[str, Optional[float]],
    data_quality: Optional[Dict] = None,
) -> Dict:
    """Generate the full dashboard_current payload."""
    quadrant = classify_quadrant(state_score, stress_score)

    return {
        "as_of": ts,
        "state_score": state_score,
        "stress_score": stress_score,
        "quadrant": quadrant,
        "key_cards": build_key_cards(levels, percentiles, flows),
        "insight_bullets": build_insight_bullets(levels, flows, percentiles),
        "scenario_implications": _QUADRANT_IMPLICATIONS.get(quadrant, []) if quadrant else [],
        "data_quality": data_quality or {},
    }


def generate_daily_brief(
    brief_date: date,
    state_score: Optional[float],
    stress_score: Optional[float],
    levels: Dict[str, Optional[float]],
    percentiles: Dict[str, Optional[float]],
    flows: Dict[str, Optional[float]],
    data_quality: Optional[Dict] = None,
) -> Dict:
    """Generate the end-of-day daily_brief_history payload."""
    quadrant = classify_quadrant(state_score, stress_score)
    headline = _QUADRANT_HEADLINES.get(quadrant, "Market data summary for the day")

    # Build body text
    cards = build_key_cards(levels, percentiles, flows)
    bullets = build_insight_bullets(levels, flows, percentiles)

    body_parts = []
    if cards:
        body_parts.append("Key levels: " + ", ".join(
            "%s=%s (P%s)" % (c["label"], c["value"] or "N/A", c["percentile"] or "N/A")
            for c in cards[:3]
        ))
    if bullets:
        body_parts.append("Observations: " + "; ".join(bullets[:3]))

    return {
        "brief_date": brief_date,
        "generated_at": datetime.now(),
        "quadrant": quadrant,
        "state_score": state_score,
        "stress_score": stress_score,
        "headline": headline,
        "body_text": ". ".join(body_parts),
        "key_metrics": {k: v for k, v in levels.items() if v is not None},
        "data_quality": data_quality or {},
    }
