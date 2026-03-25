from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from phase0.models import ProbeUniverseItem
from phase0.providers.base import classify_quote_quality, top_of_book
from phase0.providers.upstox.client import UpstoxClient


def fetch_quotes(client: UpstoxClient, instrument_keys: Sequence[str], batch_size: int = 500) -> Dict[str, Dict]:
    merged: Dict[str, Dict] = {}
    keys_list = list(instrument_keys)
    for start in range(0, len(keys_list), batch_size):
        chunk = keys_list[start : start + batch_size]
        if not chunk:
            continue
        params = {"instrument_key": ",".join(chunk)}
        response = client.get("/v2/market-quote/quotes", params=params)
        data = response.get("data") or {}
        for resp_key, payload in data.items():
            canonical = _normalize_response_key(payload.get("instrument_token") or resp_key)
            merged[canonical] = payload
    return merged


def _normalize_response_key(key: str) -> str:
    """Upstox returns colon-separated keys (NSE_INDEX:Nifty 50) but we use pipe-separated (NSE_INDEX|Nifty 50)."""
    return key.replace(":", "|", 1) if ":" in key else key


def _find_quote_payload(item: ProbeUniverseItem, quote_map: Dict[str, Dict]) -> Optional[Dict]:
    """Find quote payload for a universe item by instrument_key."""
    if item.instrument_key and item.instrument_key in quote_map:
        return quote_map[item.instrument_key]
    return None


def normalise_snapshots(
    universe: Sequence[ProbeUniverseItem],
    quote_map: Dict[str, Dict],
    snapshot_ts: datetime,
    store_raw_json: bool = False,
) -> Tuple[List[Dict], List[Dict]]:
    underlying_rows: List[Dict] = []
    option_rows: List[Dict] = []

    for item in universe:
        payload = _find_quote_payload(item, quote_map)
        if not payload:
            continue
        row_type, row = normalise_snapshot_payload(item, payload, snapshot_ts, store_raw_json)
        if row_type == "underlying":
            underlying_rows.append(row)
        else:
            option_rows.append(row)

    return underlying_rows, option_rows


def normalise_snapshot_payload(
    item: ProbeUniverseItem,
    payload: Dict,
    snapshot_ts: datetime,
    store_raw_json: bool = False,
) -> Tuple[str, Dict]:
    depth = payload.get("depth") or {}
    bid, bid_qty, ask, ask_qty = top_of_book(depth)
    ltp = payload.get("last_price")
    quote_quality = classify_quote_quality(bid, ask, ltp)

    raw_json = payload if store_raw_json else {}

    base = {
        "ts": snapshot_ts,
        "exchange": item.exchange,
        "tradingsymbol": item.tradingsymbol,
        "instrument_token": item.instrument_token,
        "instrument_key": item.instrument_key,
        "provider": item.provider,
        "raw_json": raw_json,
        "quote_quality": quote_quality,
    }

    if item.role.startswith("future") or item.role == "spot":
        return "underlying", dict(
            base,
            source_type="index" if item.role == "spot" else "future",
            last_price=ltp,
            bid=bid,
            ask=ask,
            volume=payload.get("volume"),
            oi=payload.get("oi"),
        )

    return "option", dict(
        base,
        expiry=item.expiry,
        strike=item.strike,
        option_type=item.option_type,
        bid=bid,
        ask=ask,
        ltp=ltp,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        volume=payload.get("volume"),
        oi=payload.get("oi"),
        last_trade_time=payload.get("last_trade_time"),
    )
