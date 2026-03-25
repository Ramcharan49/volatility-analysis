from __future__ import annotations

import gzip
import json
from datetime import date
from io import BytesIO
from typing import Dict, List, Optional

import requests


INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"


def download_instruments(segment_filter: Optional[str] = None) -> List[Dict]:
    response = requests.get(INSTRUMENTS_URL, timeout=60)
    response.raise_for_status()

    with gzip.open(BytesIO(response.content), "rt", encoding="utf-8") as f:
        raw_rows = json.load(f)

    rows = []
    for raw in raw_rows:
        seg = raw.get("segment") or ""
        if segment_filter and seg != segment_filter:
            continue
        rows.append(_normalize_instrument_row(raw))
    return rows


def _normalize_instrument_row(raw: Dict) -> Dict:
    expiry_str = raw.get("expiry")
    expiry = None
    if expiry_str:
        try:
            expiry = date.fromisoformat(expiry_str) if isinstance(expiry_str, str) else expiry_str
        except (ValueError, TypeError):
            expiry = None

    strike = raw.get("strike_price")
    if strike is not None:
        try:
            strike = float(strike)
        except (ValueError, TypeError):
            strike = None

    exchange_token = raw.get("exchange_token")
    if exchange_token is not None:
        try:
            exchange_token = int(exchange_token)
        except (ValueError, TypeError):
            exchange_token = None

    return {
        "instrument_key": raw.get("instrument_key") or "",
        "exchange": raw.get("exchange") or raw.get("segment") or "",
        "segment": raw.get("segment") or "",
        "tradingsymbol": raw.get("trading_symbol") or raw.get("tradingsymbol") or "",
        "name": raw.get("name") or "",
        "instrument_type": raw.get("instrument_type") or "",
        "expiry": expiry,
        "strike": strike,
        "tick_size": float(raw.get("tick_size") or 0),
        "lot_size": int(raw.get("lot_size") or raw.get("minimum_lot") or 0),
        "instrument_token": exchange_token,
        "exchange_token": exchange_token,
        "weekly": bool(raw.get("weekly")),
        "raw": raw,
    }
