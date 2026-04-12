"""NarrativeContext: the typed input to the LLM prompt builder.

Pure-data types + a `build_context()` function that populates them from the
Supabase state (dashboard_current + metric_series_1m + daily_brief_history).
Keeping this separate from the LLM call keeps the module easily testable with
a fixture dict — no network, no API keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence


# ── Metric label + grouping registry (mirrors FE + worker/daily_brief.py) ──

# Six metrics shown on the home dashboard. These are what the reader sees.
GRID_LEVEL_KEYS = ("atm_iv_7d", "atm_iv_30d", "term_7d_30d", "rr25_30d")
GRID_FLOW_KEYS = ("d_atm_iv_30d_1d", "d_rr25_30d_1d")

# Metrics that feed state_score but are NOT on the home grid.
# Included so the model can honestly explain the composite score.
COMPOSITE_ONLY_KEYS = ("bf25_30d", "front_end_dominance")

# Metrics whose raw statistical percentile is inverted for "stress-aligned"
# display. Higher raw pct = less stress (e.g., RR negative territory = fear).
STRESS_DIRECTION_INVERTED = frozenset({"rr25_30d"})

_LABELS: Dict[str, str] = {
    "atm_iv_7d": "ATM IV 7D",
    "atm_iv_30d": "ATM IV 30D",
    "atm_iv_90d": "ATM IV 90D",
    "rr25_30d": "Risk Reversal 30D",
    "bf25_30d": "Butterfly 30D",
    "term_7d_30d": "Term Spread 7D-30D",
    "front_end_dominance": "Front-End Dominance",
    "d_atm_iv_30d_1d": "Chg in 30D ATM IV",
    "d_rr25_30d_1d": "Chg in 30D Risk Reversal",
}


def metric_label(key: str) -> str:
    return _LABELS.get(key, key)


# ── Public types ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MetricEntry:
    """A level-metric reading for the prompt. Raw and stress-aligned
    percentiles are both surfaced so the model can't confuse them."""
    key: str
    label: str
    raw_value: Optional[float]
    raw_percentile: Optional[float]
    stress_aligned_percentile: Optional[float]
    surface: str  # "grid" | "composite-only"


@dataclass(frozen=True)
class FlowEntry:
    """A flow-metric (1-day change) reading."""
    key: str
    label: str
    raw_value: Optional[float]
    raw_percentile: Optional[float]


@dataclass(frozen=True)
class TrailPoint:
    """One day of regime-map trajectory."""
    day: date
    state_score: Optional[float]
    stress_score: Optional[float]
    quadrant: Optional[str]


@dataclass(frozen=True)
class NarrativeContext:
    """Everything the prompt builder needs. Serialisable to JSON for audit."""
    brief_date: date
    quadrant: Optional[str]
    state_score: Optional[float]
    stress_score: Optional[float]
    grid_metrics: List[MetricEntry] = field(default_factory=list)
    composite_metrics: List[MetricEntry] = field(default_factory=list)
    flow_metrics: List[FlowEntry] = field(default_factory=list)
    trail: List[TrailPoint] = field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _stress_aligned(key: str, raw_pct: Optional[float]) -> Optional[float]:
    """Return the stress-oriented percentile: higher = more stress."""
    if raw_pct is None:
        return None
    if key in STRESS_DIRECTION_INVERTED:
        return 100.0 - float(raw_pct)
    return float(raw_pct)


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Loader: assemble context from Supabase state ────────────────────────────

def build_context(
    conn,
    brief_date: date,
    trail_days: int = 7,
) -> NarrativeContext:
    """Build a NarrativeContext by reading live Supabase state.

    Uses only read-only SELECTs. The `conn` is a psycopg connection (caller
    owns the lifecycle). Any missing data is represented as None so the
    prompt can degrade gracefully.
    """
    # 1. Dashboard snapshot (gives quadrant, state/stress, 5 level cards).
    dashboard = _fetch_dashboard_row(conn)
    quadrant = dashboard.get("quadrant") if dashboard else None
    state_score = _as_float(dashboard.get("state_score")) if dashboard else None
    stress_score = _as_float(dashboard.get("stress_score")) if dashboard else None
    cards_by_key = _index_cards(dashboard.get("key_cards_json") if dashboard else None)

    # 2. FED + flow-metric (+bf25 if missing from cards) snapshot from metric_series_1m.
    latest_levels = _fetch_latest_level_snapshot(
        conn,
        metric_keys=("front_end_dominance", "bf25_30d"),
    )
    latest_flows = _fetch_latest_flow_snapshot(
        conn,
        metric_keys=GRID_FLOW_KEYS,
        window_code="1d",
    )

    # 3. Assemble grid metrics (4 level + 2 are flows handled separately).
    grid_metrics: List[MetricEntry] = []
    for key in GRID_LEVEL_KEYS:
        card = cards_by_key.get(key, {})
        raw_pct = _as_float(card.get("percentile"))
        grid_metrics.append(MetricEntry(
            key=key,
            label=metric_label(key),
            raw_value=_as_float(card.get("raw_value")),
            raw_percentile=raw_pct,
            stress_aligned_percentile=_stress_aligned(key, raw_pct),
            surface="grid",
        ))

    # 4. Composite-only metrics (inform state_score but hidden from the grid).
    composite_metrics: List[MetricEntry] = []
    for key in COMPOSITE_ONLY_KEYS:
        card = cards_by_key.get(key)
        latest = latest_levels.get(key, {})
        raw_value = _as_float(card.get("raw_value")) if card else _as_float(latest.get("value"))
        raw_pct = _as_float(card.get("percentile")) if card else _as_float(latest.get("percentile"))
        composite_metrics.append(MetricEntry(
            key=key,
            label=metric_label(key),
            raw_value=raw_value,
            raw_percentile=raw_pct,
            stress_aligned_percentile=_stress_aligned(key, raw_pct),
            surface="composite-only",
        ))

    # 5. Flow metrics (grid-visible momentum row).
    flow_metrics: List[FlowEntry] = []
    for key in GRID_FLOW_KEYS:
        latest = latest_flows.get(key, {})
        flow_metrics.append(FlowEntry(
            key=key,
            label=metric_label(key),
            raw_value=_as_float(latest.get("value")),
            raw_percentile=_as_float(latest.get("percentile")),
        ))

    # 6. 7-day regime trail — state + stress by day + today's brief quadrant.
    trail = _fetch_regime_trail(conn, end_date=brief_date, days=trail_days)

    return NarrativeContext(
        brief_date=brief_date,
        quadrant=quadrant,
        state_score=state_score,
        stress_score=stress_score,
        grid_metrics=grid_metrics,
        composite_metrics=composite_metrics,
        flow_metrics=flow_metrics,
        trail=trail,
    )


# ── SQL helpers ─────────────────────────────────────────────────────────────

def _fetch_dashboard_row(conn) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT quadrant, state_score, stress_score, key_cards_json
        FROM public.dashboard_current
        WHERE id = 1
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "quadrant": row[0],
            "state_score": row[1],
            "stress_score": row[2],
            "key_cards_json": row[3],
        }


def _index_cards(cards: Any) -> Dict[str, Dict[str, Any]]:
    if not cards:
        return {}
    if isinstance(cards, str):
        # jsonb columns come back as parsed objects; belt-and-braces parse.
        import json
        try:
            cards = json.loads(cards)
        except Exception:
            return {}
    result: Dict[str, Dict[str, Any]] = {}
    for card in cards:
        key = card.get("metric_key")
        if key:
            result[key] = card
    return result


def _fetch_latest_level_snapshot(
    conn,
    metric_keys: Sequence[str],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Latest value + percentile per level metric (any tenor code, no window)."""
    sql = """
        SELECT DISTINCT ON (metric_key) metric_key, value, percentile, ts
        FROM public.metric_series_1m
        WHERE metric_key = ANY(%s)
          AND window_code IS NULL
        ORDER BY metric_key, ts DESC
    """
    result: Dict[str, Dict[str, Optional[float]]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (list(metric_keys),))
        for row in cur.fetchall():
            result[row[0]] = {
                "value": row[1],
                "percentile": row[2],
            }
    return result


def _fetch_latest_flow_snapshot(
    conn,
    metric_keys: Sequence[str],
    window_code: str = "1d",
) -> Dict[str, Dict[str, Optional[float]]]:
    """Latest value + percentile per flow metric, filtered to the given window."""
    sql = """
        SELECT DISTINCT ON (metric_key) metric_key, value, percentile, ts
        FROM public.metric_series_1m
        WHERE metric_key = ANY(%s)
          AND window_code = %s
        ORDER BY metric_key, ts DESC
    """
    result: Dict[str, Dict[str, Optional[float]]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (list(metric_keys), window_code))
        for row in cur.fetchall():
            result[row[0]] = {
                "value": row[1],
                "percentile": row[2],
            }
    return result


def _fetch_regime_trail(
    conn,
    end_date: date,
    days: int,
) -> List[TrailPoint]:
    """Return the last `days` trading-day snapshots of (state, stress, quadrant).

    Uses daily_brief_history.quadrant for historical classification (authoritative)
    and metric_series_1m for state/stress (aggregated as latest-sample-per-day).
    Today's row may or may not exist in daily_brief_history yet; we fall back to
    dashboard_current.quadrant for today if needed.
    """
    start_date = end_date - timedelta(days=days * 2)  # buffer for weekends/holidays

    quadrant_by_day = _fetch_quadrants_by_day(conn, start_date, end_date)
    scores_by_day = _fetch_daily_scores(conn, start_date, end_date)

    all_days = sorted(set(quadrant_by_day.keys()) | set(scores_by_day.keys()))
    all_days = all_days[-days:]

    trail: List[TrailPoint] = []
    for d in all_days:
        scores = scores_by_day.get(d, {})
        trail.append(TrailPoint(
            day=d,
            state_score=_as_float(scores.get("state_score")),
            stress_score=_as_float(scores.get("stress_score")),
            quadrant=quadrant_by_day.get(d),
        ))
    return trail


def _fetch_quadrants_by_day(conn, start_date: date, end_date: date) -> Dict[date, str]:
    sql = """
        SELECT brief_date, quadrant
        FROM public.daily_brief_history
        WHERE brief_date BETWEEN %s AND %s
    """
    result: Dict[date, str] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (start_date, end_date))
        for row in cur.fetchall():
            if row[1]:
                result[row[0]] = row[1]
    return result


def _fetch_daily_scores(conn, start_date: date, end_date: date) -> Dict[date, Dict[str, float]]:
    """Latest sample per day of state_score + stress_score."""
    sql = """
        SELECT DISTINCT ON (ts::date, metric_key)
            ts::date AS day, metric_key, value
        FROM public.metric_series_1m
        WHERE metric_key IN ('state_score', 'stress_score')
          AND ts::date BETWEEN %s AND %s
        ORDER BY ts::date, metric_key, ts DESC
    """
    result: Dict[date, Dict[str, float]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (start_date, end_date))
        for row in cur.fetchall():
            day, metric_key, value = row
            if value is None:
                continue
            result.setdefault(day, {})[metric_key] = float(value)
    return result
