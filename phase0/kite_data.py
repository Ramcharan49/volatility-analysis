from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from phase0.models import ProbeUniverseItem
from phase0.time_utils import indian_timezone


IST = indian_timezone()


def fetch_quotes(kite, instruments: Sequence[str], batch_size: int = 200) -> Dict[str, Dict]:
    merged: Dict[str, Dict] = {}
    for start in range(0, len(instruments), batch_size):
        chunk = list(instruments[start : start + batch_size])
        if not chunk:
            continue
        merged.update(kite.quote(chunk))
    return merged


def fetch_historical_sample(
    kite,
    instrument_token: int,
    days: int = 7,
    interval: str = "minute",
    continuous: bool = False,
    oi: bool = True,
) -> List[Dict]:
    now = datetime.now(IST)
    from_date = now - timedelta(days=days)
    return kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_date,
        to_date=now,
        interval=interval,
        continuous=continuous,
        oi=oi,
    )


def normalise_snapshots(
    universe: Sequence[ProbeUniverseItem],
    quote_map: Dict[str, Dict],
    snapshot_ts: datetime,
) -> Tuple[List[Dict], List[Dict]]:
    underlying_rows: List[Dict] = []
    option_rows: List[Dict] = []

    for item in universe:
        payload = quote_map.get(item.quote_symbol())
        if not payload:
            continue
        row_type, row = normalise_snapshot_payload(item, payload, snapshot_ts)
        if row_type == "underlying":
            underlying_rows.append(row)
        else:
            option_rows.append(row)

    return underlying_rows, option_rows


def normalise_snapshot_payload(
    item: ProbeUniverseItem,
    payload: Dict,
    snapshot_ts: datetime,
) -> Tuple[str, Dict]:
    bid, bid_qty, ask, ask_qty = top_of_book(payload)
    quote_quality = classify_quote_quality(bid, ask, payload.get("last_price"))
    instrument_token = payload.get("instrument_token", item.instrument_token)

    base = {
        "ts": snapshot_ts,
        "exchange": item.exchange,
        "tradingsymbol": item.tradingsymbol,
        "instrument_token": instrument_token,
        "raw_json": payload,
        "quote_quality": quote_quality,
    }

    if item.role.startswith("future") or item.role == "spot":
        return "underlying", dict(
            base,
            source_type="index" if item.role == "spot" else "future",
            last_price=payload.get("last_price"),
            bid=bid,
            ask=ask,
            volume=payload.get("volume") or payload.get("volume_traded"),
            oi=payload.get("oi"),
        )

    return "option", dict(
        base,
        expiry=item.expiry,
        strike=item.strike,
        option_type=item.option_type,
        bid=bid,
        ask=ask,
        ltp=payload.get("last_price"),
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        volume=payload.get("volume") or payload.get("volume_traded"),
        oi=payload.get("oi"),
        last_trade_time=payload.get("last_trade_time"),
    )


def pick_historical_targets(universe: Sequence[ProbeUniverseItem], spot_reference: float) -> List[ProbeUniverseItem]:
    futures = [item for item in universe if item.role == "future_front"]
    options = [item for item in universe if item.role == "option" and item.expiry is not None and item.strike is not None]
    if not options:
        return futures

    earliest_expiry = min(item.expiry for item in options if item.expiry is not None)
    scoped = [item for item in options if item.expiry == earliest_expiry]
    ce = [item for item in scoped if item.option_type == "CE"]
    pe = [item for item in scoped if item.option_type == "PE"]

    nearest_ce = min(ce, key=lambda item: abs(float(item.strike or 0) - spot_reference)) if ce else None
    nearest_pe = min(pe, key=lambda item: abs(float(item.strike or 0) - spot_reference)) if pe else None

    targets = list(futures)
    if nearest_ce:
        targets.append(nearest_ce)
    if nearest_pe:
        targets.append(nearest_pe)
    return targets


def top_of_book(payload: Dict) -> Tuple[Optional[float], Optional[int], Optional[float], Optional[int]]:
    depth = payload.get("depth") or {}
    best_buy = (depth.get("buy") or [None])[0] or {}
    best_sell = (depth.get("sell") or [None])[0] or {}
    bid = best_buy.get("price")
    ask = best_sell.get("price")
    bid_qty = best_buy.get("quantity")
    ask_qty = best_sell.get("quantity")
    return bid, bid_qty, ask, ask_qty


def classify_quote_quality(bid: Optional[float], ask: Optional[float], ltp: Optional[float]) -> str:
    if bid and ask and ask >= bid:
        mid = (bid + ask) / 2.0
        spread = ask - bid
        if mid > 0 and (spread / mid) <= 0.03:
            return "valid_mid"
        return "wide_mid"
    if ltp and ltp > 0:
        return "ltp_fallback"
    return "invalid"
