from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import quote as url_quote

from phase0.providers.upstox.client import UpstoxClient


def fetch_historical_candles(
    client: UpstoxClient,
    instrument_key: str,
    interval: str = "1minute",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    to_str = (to_date or date.today()).isoformat()
    from_str = from_date.isoformat() if from_date else to_str
    encoded_key = url_quote(instrument_key, safe="")
    path = "/v2/historical-candle/%s/%s/%s/%s" % (encoded_key, interval, to_str, from_str)
    response = client.get(path)
    return _parse_candles(response)


def fetch_expired_expiries(client: UpstoxClient, instrument_key: str) -> List[str]:
    response = client.get("/v2/expired-instruments/expiries", params={"instrument_key": instrument_key})
    return response.get("data") or []


def fetch_expired_option_contracts(client: UpstoxClient, instrument_key: str, expiry_date: str) -> List[Dict]:
    response = client.get(
        "/v2/expired-instruments/option/contract",
        params={"instrument_key": instrument_key, "expiry_date": expiry_date},
    )
    return response.get("data") or []


def fetch_expired_historical_candles(
    client: UpstoxClient,
    expired_instrument_key: str,
    interval: str = "day",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    to_str = (to_date or date.today()).isoformat()
    from_str = from_date.isoformat() if from_date else to_str
    encoded_key = url_quote(expired_instrument_key, safe="")
    path = "/v2/expired-instruments/historical-candle/%s/%s/%s/%s" % (encoded_key, interval, to_str, from_str)
    response = client.get(path)
    return _parse_candles(response)


def _parse_candles(response: Dict) -> List[Dict]:
    data = response.get("data") or {}
    raw_candles = data.get("candles") or []
    candles = []
    for candle in raw_candles:
        if len(candle) < 6:
            continue
        candles.append({
            "date": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": int(candle[5]),
            "oi": int(candle[6]) if len(candle) > 6 else 0,
        })
    return candles
