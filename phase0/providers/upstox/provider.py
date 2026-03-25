from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from phase0.config import Settings
from phase0.models import SessionState
from phase0.providers.upstox.auth import (
    authenticate_interactive,
    ensure_valid_session,
    exchange_code_for_session,
    load_session_state,
)
from phase0.providers.upstox.client import UpstoxClient
from phase0.providers.upstox.history import (
    fetch_expired_expiries,
    fetch_expired_historical_candles,
    fetch_expired_option_contracts,
    fetch_historical_candles,
)
from phase0.providers.upstox.instruments import download_instruments
from phase0.providers.upstox.quotes import fetch_quotes as _fetch_quotes, _normalize_response_key
from phase0.providers.upstox.websocket import UpstoxWebSocket


class UpstoxProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[UpstoxClient] = None
        self._session: Optional[SessionState] = None

    @property
    def client(self) -> UpstoxClient:
        if self._client is None:
            raise RuntimeError("Provider not authenticated. Call ensure_session() first.")
        return self._client

    def authenticate(self, settings: Settings, open_browser: bool = True) -> SessionState:
        session = authenticate_interactive(settings, open_browser=open_browser)
        self._session = session
        self._client = UpstoxClient(session.access_token)
        return session

    def exchange_code(self, settings: Settings, code: str) -> SessionState:
        session = exchange_code_for_session(settings, code)
        self._session = session
        self._client = UpstoxClient(session.access_token)
        return session

    def load_session(self, settings: Settings) -> Optional[SessionState]:
        return load_session_state(settings)

    def ensure_session(self, settings: Settings) -> SessionState:
        session = ensure_valid_session(settings)
        self._session = session
        self._client = UpstoxClient(session.access_token)
        return session

    def sync_instruments(self) -> List[Dict]:
        return download_instruments(segment_filter=self.settings.derivative_segment)

    def fetch_quotes(self, instrument_keys: List[str], batch_size: int = 500) -> Dict[str, Dict]:
        return _fetch_quotes(self.client, instrument_keys, batch_size=batch_size)

    def fetch_historical(
        self,
        instrument_key: str,
        interval: str = "1minute",
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        return fetch_historical_candles(self.client, instrument_key, interval, from_date, to_date)

    def fetch_expired_history(
        self,
        expired_key: str,
        interval: str = "day",
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        return fetch_expired_historical_candles(self.client, expired_key, interval, from_date, to_date)

    def get_ltp(self, instrument_keys: List[str]) -> Dict[str, float]:
        response = self.client.get("/v2/market-quote/ltp", params={"instrument_key": ",".join(instrument_keys)})
        data = response.get("data") or {}
        return {_normalize_response_key(key): float(val["last_price"]) for key, val in data.items() if val.get("last_price") is not None}

    def get_expired_expiries(self, instrument_key: str) -> List[str]:
        return fetch_expired_expiries(self.client, instrument_key)

    def get_expired_option_contracts(self, instrument_key: str, expiry_date: str) -> List[Dict]:
        return fetch_expired_option_contracts(self.client, instrument_key, expiry_date)

    def create_websocket(self, access_token: str, on_ticks, on_connect, on_error, on_reconnect=None) -> UpstoxWebSocket:
        return UpstoxWebSocket(
            access_token=access_token,
            on_ticks=on_ticks,
            on_connect=on_connect,
            on_error=on_error,
            on_reconnect=on_reconnect,
        )
