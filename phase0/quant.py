from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from phase0.models import ExpiryNode
from phase0.time_utils import indian_timezone


IST = indian_timezone()
TARGET_DELTA = 0.25
TARGET_DELTA_10 = 0.10
QUALITY_SCORE_MAP = {"high": 1.0, "medium": 0.6, "low": 0.25, "null": 0.0}
RRBF_SCORE_MAP = {"high": 1.0, "low": 0.5, "null": 0.0}


def norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def black76_price(option_type: str, forward: float, strike: float, time_to_expiry: float, rate: float, sigma: float) -> float:
    if time_to_expiry <= 0 or sigma <= 0 or forward <= 0 or strike <= 0:
        intrinsic = max(0.0, forward - strike) if option_type == "CE" else max(0.0, strike - forward)
        return math.exp(-rate * max(time_to_expiry, 0.0)) * intrinsic

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * time_to_expiry) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    discount = math.exp(-rate * time_to_expiry)

    if option_type == "CE":
        return discount * (forward * norm_cdf(d1) - strike * norm_cdf(d2))
    return discount * (strike * norm_cdf(-d2) - forward * norm_cdf(-d1))


def black76_delta(option_type: str, forward: float, strike: float, time_to_expiry: float, sigma: float) -> Optional[float]:
    if time_to_expiry <= 0 or sigma <= 0 or forward <= 0 or strike <= 0:
        return None
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * time_to_expiry) / (sigma * sqrt_t)
    if option_type == "CE":
        return norm_cdf(d1)
    return norm_cdf(d1) - 1.0


def implied_volatility(
    option_type: str,
    option_price: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    tolerance: float = 1e-6,
    max_iterations: int = 120,
) -> Optional[float]:
    if option_price is None or option_price <= 0:
        return None
    if forward <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None

    intrinsic = math.exp(-rate * time_to_expiry) * (
        max(0.0, forward - strike) if option_type == "CE" else max(0.0, strike - forward)
    )
    if option_price < intrinsic - 1e-6:
        return None

    low = 1e-6
    high = 5.0
    price_at_high = black76_price(option_type, forward, strike, time_to_expiry, rate, high)
    while price_at_high < option_price and high < 10.0:
        high *= 1.5
        price_at_high = black76_price(option_type, forward, strike, time_to_expiry, rate, high)

    if price_at_high < option_price:
        return None

    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        model = black76_price(option_type, forward, strike, time_to_expiry, rate, mid)
        error = model - option_price
        if abs(error) <= tolerance:
            return mid
        if error > 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2.0


def compute_expiry_nodes(
    option_rows: Sequence[Dict],
    snapshot_ts: datetime,
    future_price: Optional[float],
    spot_price: Optional[float],
    rate: float,
    allow_ltp_fallback: bool = False,
) -> List[ExpiryNode]:
    grouped: Dict[date, List[Dict]] = defaultdict(list)
    for row in option_rows:
        expiry = row.get("expiry")
        if expiry is None:
            continue
        grouped[expiry].append(row)

    nodes: List[ExpiryNode] = []
    for expiry, rows in sorted(grouped.items(), key=lambda item: item[0]):
        node = compute_expiry_node(
            rows,
            expiry,
            snapshot_ts,
            future_price,
            spot_price,
            rate,
            allow_ltp_fallback=allow_ltp_fallback,
        )
        if node:
            nodes.append(node)
    return nodes


def compute_expiry_node(
    option_rows: Sequence[Dict],
    expiry: date,
    snapshot_ts: datetime,
    future_price: Optional[float],
    spot_price: Optional[float],
    rate: float,
    allow_ltp_fallback: bool = False,
) -> Optional[ExpiryNode]:
    time_to_expiry = _time_to_expiry_years(expiry, snapshot_ts)
    if time_to_expiry <= 0:
        return None

    cleaned: List[Dict] = []
    grouped_by_strike: Dict[float, Dict[str, Dict]] = defaultdict(dict)
    available_strikes = sorted({float(row["strike"]) for row in option_rows if row.get("strike") is not None})

    for row in option_rows:
        price = cleaned_option_price(row, allow_ltp_fallback=allow_ltp_fallback)
        if price is None:
            continue
        row_copy = dict(row)
        row_copy["clean_price"] = price
        row_copy["liquidity_score"] = float(row.get("volume") or 0) + float(row.get("oi") or 0)
        row_copy["used_ltp_fallback"] = bool(row.get("quote_quality") == "ltp_fallback")
        cleaned.append(row_copy)
        grouped_by_strike[float(row_copy["strike"])][row_copy["option_type"]] = row_copy

    if not cleaned or not available_strikes:
        return None

    reference_price = future_price or spot_price
    parity_candidates: List[Tuple[float, float, float]] = []
    for strike, pair in grouped_by_strike.items():
        call_row = pair.get("CE")
        put_row = pair.get("PE")
        if not call_row or not put_row:
            continue
        if call_row.get("quote_quality") != "valid_mid" or put_row.get("quote_quality") != "valid_mid":
            continue
        candidate_forward = strike + math.exp(rate * time_to_expiry) * (call_row["clean_price"] - put_row["clean_price"])
        distance = abs(strike - reference_price) if reference_price else abs(strike)
        liquidity = -(call_row["liquidity_score"] + put_row["liquidity_score"])
        parity_candidates.append((distance, liquidity, candidate_forward))

    forward = None
    forward_source = "invalid"
    forward_quality = "null"
    if parity_candidates:
        selected = sorted(parity_candidates)[:3]
        forward = median(candidate[2] for candidate in selected)
        forward_source = "parity"
        forward_quality = "high" if len(selected) >= 2 else "medium"
    elif future_price and future_price > 0:
        forward = future_price
        forward_source = "future_fallback"
        forward_quality = "low"

    if not forward or forward <= 0:
        return None

    valid_options: List[Dict] = []
    for row in cleaned:
        sigma = implied_volatility(row["option_type"], row["clean_price"], forward, float(row["strike"]), time_to_expiry, rate)
        if sigma is None:
            continue
        delta = black76_delta(row["option_type"], forward, float(row["strike"]), time_to_expiry, sigma)
        row_copy = dict(row)
        row_copy["iv"] = sigma
        row_copy["delta"] = delta
        valid_options.append(row_copy)

    if not valid_options:
        return None

    atm_strike = min(available_strikes, key=lambda strike: abs(strike - forward))
    atm_iv, atm_quality = _resolve_atm_iv(valid_options, atm_strike)

    calls = [row for row in valid_options if row["option_type"] == "CE" and row.get("delta") is not None]
    puts = [row for row in valid_options if row["option_type"] == "PE" and row.get("delta") is not None]
    iv_25c, call_bracketed = interpolate_iv_by_delta(calls, TARGET_DELTA, use_abs_delta=False)
    iv_25p, put_bracketed = interpolate_iv_by_delta(puts, TARGET_DELTA, use_abs_delta=True)

    iv_10c, call_10_bracketed = interpolate_iv_by_delta(calls, TARGET_DELTA_10, use_abs_delta=False)
    iv_10p, put_10_bracketed = interpolate_iv_by_delta(puts, TARGET_DELTA_10, use_abs_delta=True)

    rr_bf_quality = "null"
    bracketed_25d = bool(call_bracketed and put_bracketed)
    bracketed_10d = bool(call_10_bracketed and put_10_bracketed)
    if iv_25c is not None and iv_25p is not None:
        rr_bf_quality = "high" if bracketed_25d else "low"

    wing_10_quality = "null"
    if iv_10c is not None and iv_10p is not None:
        wing_10_quality = "high" if bracketed_10d else ("medium" if (call_10_bracketed or put_10_bracketed) else "low")

    rr25 = (iv_25c - iv_25p) if iv_25c is not None and iv_25p is not None else None
    bf25 = (0.5 * (iv_25c + iv_25p) - atm_iv) if iv_25c is not None and iv_25p is not None and atm_iv is not None else None
    used_ltp_fallback = any(bool(row.get("used_ltp_fallback")) for row in valid_options)

    quality_score = round(
        (0.40 * QUALITY_SCORE_MAP[forward_quality])
        + (0.35 * QUALITY_SCORE_MAP[atm_quality])
        + (0.25 * RRBF_SCORE_MAP[rr_bf_quality]),
        3,
    )

    return ExpiryNode(
        ts=snapshot_ts,
        expiry=expiry,
        dte_days=time_to_expiry * 365.0,
        forward=forward,
        atm_strike=atm_strike,
        atm_iv=atm_iv,
        iv_25c=iv_25c,
        iv_25p=iv_25p,
        iv_10c=iv_10c,
        iv_10p=iv_10p,
        rr25=rr25,
        bf25=bf25,
        source_count=len(valid_options),
        quality_score=quality_score,
        method_json={
            "pricing_model": "black_76",
            "delta_convention": "forward",
            "target_delta": TARGET_DELTA,
            "forward_source": forward_source,
            "forward_quality": forward_quality,
            "atm_quality": atm_quality,
            "rr_bf_quality": rr_bf_quality,
            "used_ltp_fallback": used_ltp_fallback,
            "bracketed_25d": bracketed_25d,
            "bracketed_10d": bracketed_10d,
            "wing_10_quality": wing_10_quality,
            "stress_window": "1d",
        },
    )


def cleaned_option_price(row: Dict, allow_ltp_fallback: bool = False) -> Optional[float]:
    bid = row.get("bid")
    ask = row.get("ask")
    ltp = row.get("ltp")
    quality = row.get("quote_quality")

    if quality == "valid_mid" and bid is not None and ask is not None and ask >= bid:
        mid = (float(bid) + float(ask)) / 2.0
        if mid > 0:
            return mid
    if allow_ltp_fallback and quality == "ltp_fallback" and ltp and ltp > 0:
        return float(ltp)
    return None


def interpolate_iv_by_delta(options: Sequence[Dict], target_delta: float, use_abs_delta: bool) -> Tuple[Optional[float], bool]:
    keyed = []
    for row in options:
        delta = row.get("delta")
        iv = row.get("iv")
        if delta is None or iv is None:
            continue
        key = abs(float(delta)) if use_abs_delta else float(delta)
        keyed.append((key, float(iv)))

    keyed = sorted(keyed, key=lambda item: item[0])
    if not keyed:
        return None, False
    if len(keyed) == 1:
        return keyed[0][1], False

    for index in range(len(keyed) - 1):
        left_delta, left_iv = keyed[index]
        right_delta, right_iv = keyed[index + 1]
        if left_delta <= target_delta <= right_delta:
            if right_delta == left_delta:
                return left_iv, True
            weight = (target_delta - left_delta) / (right_delta - left_delta)
            return left_iv + (right_iv - left_iv) * weight, True

    return min(keyed, key=lambda item: abs(item[0] - target_delta))[1], False


def average(values: Sequence[Optional[float]]) -> Optional[float]:
    scoped = [value for value in values if value is not None]
    if not scoped:
        return None
    return sum(scoped) / len(scoped)


def _resolve_atm_iv(valid_options: Sequence[Dict], atm_strike: float) -> Tuple[Optional[float], str]:
    scoped = [row for row in valid_options if float(row["strike"]) == atm_strike]
    calls = [row["iv"] for row in scoped if row["option_type"] == "CE" and row.get("iv") is not None]
    puts = [row["iv"] for row in scoped if row["option_type"] == "PE" and row.get("iv") is not None]
    if calls and puts:
        return average([calls[0], puts[0]]), "high"
    if calls or puts:
        return (calls or puts)[0], "medium"

    strike_to_iv = {}
    for row in valid_options:
        strike = float(row["strike"])
        strike_to_iv.setdefault(strike, []).append(float(row["iv"]))

    below = sorted((strike, average(values)) for strike, values in strike_to_iv.items() if strike < atm_strike and average(values) is not None)
    above = sorted((strike, average(values)) for strike, values in strike_to_iv.items() if strike > atm_strike and average(values) is not None)
    if not below or not above:
        return None, "null"

    left_strike, left_iv = below[-1]
    right_strike, right_iv = above[0]
    if left_iv is None or right_iv is None or right_strike == left_strike:
        return None, "null"

    weight = (atm_strike - left_strike) / (right_strike - left_strike)
    return left_iv + (right_iv - left_iv) * weight, "low"


def _time_to_expiry_years(expiry: date, snapshot_ts: datetime) -> float:
    expiry_dt = datetime.combine(expiry, time(hour=15, minute=30), tzinfo=IST)
    delta = expiry_dt - snapshot_ts.astimezone(IST)
    return max(delta.total_seconds() / (365.0 * 24.0 * 60.0 * 60.0), 1e-6)
