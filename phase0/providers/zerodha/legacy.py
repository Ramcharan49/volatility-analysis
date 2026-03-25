"""
Legacy Zerodha (Kite Connect) code — preserved as reference.
Original source: phase0/session.py and phase0/kite_data.py.

Not actively used. To reactivate, implement MarketDataProvider Protocol
wrapping these functions.
"""
from __future__ import annotations

import json
import webbrowser
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

from phase0.models import ProbeUniverseItem
from phase0.time_utils import indian_timezone


IST = indian_timezone()


# ---------------------------------------------------------------------------
# Session management (from session.py)
# ---------------------------------------------------------------------------

def build_kite_client(api_key: str, access_token: Optional[str] = None):
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=api_key)
    if access_token:
        kite.set_access_token(access_token)
    return kite


def authenticate_interactive_zerodha(api_key: str, api_secret: str, redirect_url: str, session_state_path: Path, open_browser: bool = True):
    from kiteconnect import KiteConnect
    state = {"request_token": None}
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    parsed = urlparse(redirect_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    path = parsed.path or "/"

    handler = _build_callback_handler(path, state)
    server = HTTPServer((host, port), handler)

    if open_browser:
        webbrowser.open(login_url)
    else:
        print("Open this URL manually:\n%s" % login_url)

    print("Waiting for Zerodha login callback...")
    server.handle_request()
    server.server_close()

    request_token = state["request_token"]
    if not request_token:
        raise RuntimeError("No request_token received from Zerodha callback.")

    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]
    kite.set_access_token(access_token)
    profile = kite.profile()

    login_time = datetime.now(IST)
    return {
        "access_token": access_token,
        "user_id": profile.get("user_id") or "",
        "user_name": profile.get("user_name") or "",
        "email": profile.get("email"),
        "login_time": login_time,
        "expires_at": _next_session_expiry(login_time),
    }


def _next_session_expiry(login_time: datetime) -> datetime:
    next_day = login_time.astimezone(IST).date() + timedelta(days=1)
    return datetime.combine(next_day, time(hour=6, minute=0), tzinfo=IST)


def _build_callback_handler(callback_path: str, state: Dict[str, Optional[str]]):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            query = parse_qs(parsed.query)
            request_token = query.get("request_token", [None])[0]
            status = query.get("status", [None])[0]

            if request_token:
                state["request_token"] = request_token
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Login successful</h2>"
                    b"<p>request_token received. You can close this tab.</p></body></html>"
                )
                return

            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            body = "<html><body><h2>No request_token</h2><p>Status: %s</p></body></html>" % status
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args) -> None:
            return

    return CallbackHandler


# ---------------------------------------------------------------------------
# Data functions (from kite_data.py)
# ---------------------------------------------------------------------------

def fetch_quotes_zerodha(kite, instruments: Sequence[str], batch_size: int = 200) -> Dict[str, Dict]:
    merged: Dict[str, Dict] = {}
    for start in range(0, len(instruments), batch_size):
        chunk = list(instruments[start : start + batch_size])
        if not chunk:
            continue
        merged.update(kite.quote(chunk))
    return merged


def fetch_historical_sample_zerodha(
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


def normalise_snapshot_payload_zerodha(
    item: ProbeUniverseItem,
    payload: Dict,
    snapshot_ts: datetime,
) -> Tuple[str, Dict]:
    bid, bid_qty, ask, ask_qty = top_of_book_zerodha(payload)
    quote_quality = classify_quote_quality_zerodha(bid, ask, payload.get("last_price"))
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


def top_of_book_zerodha(payload: Dict) -> Tuple[Optional[float], Optional[int], Optional[float], Optional[int]]:
    depth = payload.get("depth") or {}
    best_buy = (depth.get("buy") or [None])[0] or {}
    best_sell = (depth.get("sell") or [None])[0] or {}
    bid = best_buy.get("price")
    ask = best_sell.get("price")
    bid_qty = best_buy.get("quantity")
    ask_qty = best_sell.get("quantity")
    return bid, bid_qty, ask, ask_qty


def classify_quote_quality_zerodha(bid: Optional[float], ask: Optional[float], ltp: Optional[float]) -> str:
    if bid and ask and ask >= bid:
        mid = (bid + ask) / 2.0
        spread = ask - bid
        if mid > 0 and (spread / mid) <= 0.03:
            return "valid_mid"
        return "wide_mid"
    if ltp and ltp > 0:
        return "ltp_fallback"
    return "invalid"
