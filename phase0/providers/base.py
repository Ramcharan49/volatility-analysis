from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from phase0.models import SessionState


class MarketDataProvider(Protocol):
    """Provider-agnostic interface for market data access."""

    def authenticate(self, settings) -> SessionState: ...
    def load_session(self, settings) -> Optional[SessionState]: ...
    def ensure_session(self, settings) -> SessionState: ...

    def sync_instruments(self) -> List[Dict]: ...
    def fetch_quotes(self, instrument_keys: List[str], batch_size: int = 500) -> Dict[str, Dict]: ...
    def fetch_historical(self, instrument_key: str, interval: str, from_date, to_date) -> List[Dict]: ...
    def fetch_expired_history(self, expired_key: str, interval: str, from_date, to_date) -> List[Dict]: ...
    def get_ltp(self, instrument_keys: List[str]) -> Dict[str, float]: ...
    def create_websocket(self, access_token: str, on_ticks, on_connect, on_error, on_reconnect) -> Any: ...


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


def top_of_book(depth: Dict) -> Tuple[Optional[float], Optional[int], Optional[float], Optional[int]]:
    buy_levels = depth.get("buy") or [None]
    sell_levels = depth.get("sell") or [None]
    best_buy = buy_levels[0] or {}
    best_sell = sell_levels[0] or {}
    bid = best_buy.get("price")
    ask = best_sell.get("price")
    bid_qty = best_buy.get("quantity")
    ask_qty = best_sell.get("quantity")
    return bid, bid_qty, ask, ask_qty
