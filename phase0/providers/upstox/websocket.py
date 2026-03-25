from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests

try:
    import websockets
    import websockets.sync.client as ws_sync
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from phase0.providers.upstox.client import UpstoxClient


FEED_AUTH_URL = "https://api.upstox.com/v2/feed/market-data-feed/authorize"


def get_feed_url(access_token: str) -> str:
    response = requests.get(
        FEED_AUTH_URL,
        headers={"Authorization": "Bearer %s" % access_token, "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError("Feed auth failed (%s): %s" % (response.status_code, response.text[:200]))
    data = response.json()
    url = (data.get("data") or {}).get("authorizedRedirectUri")
    if not url:
        raise RuntimeError("No authorizedRedirectUri in feed auth response")
    return url


class UpstoxWebSocket:
    def __init__(
        self,
        access_token: str,
        on_ticks: Callable,
        on_connect: Callable,
        on_error: Callable,
        on_reconnect: Optional[Callable] = None,
    ):
        if not HAS_WEBSOCKETS:
            raise RuntimeError("websockets library is not installed. Install requirements-phase0.txt.")
        self.access_token = access_token
        self.on_ticks = on_ticks
        self.on_connect = on_connect
        self.on_error = on_error
        self.on_reconnect = on_reconnect
        self._ws = None
        self._thread = None
        self._stop_event = threading.Event()
        self._instrument_keys: List[str] = []

    def connect(self, threaded: bool = True) -> None:
        if threaded:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._run_loop()

    def subscribe(self, instrument_keys: Sequence[str]) -> None:
        self._instrument_keys = list(instrument_keys)
        if self._ws:
            self._send_subscribe()

    def set_mode(self, mode: str, instrument_keys: Sequence[str]) -> None:
        pass

    def close(self) -> None:
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _run_loop(self) -> None:
        reconnect_count = 0
        while not self._stop_event.is_set():
            try:
                feed_url = get_feed_url(self.access_token)
                self._ws = ws_sync.connect(feed_url, additional_headers={
                    "Authorization": "Bearer %s" % self.access_token,
                })
                self.on_connect(self, None)
                if self._instrument_keys:
                    self._send_subscribe()

                while not self._stop_event.is_set():
                    try:
                        message = self._ws.recv(timeout=5)
                    except TimeoutError:
                        continue
                    except Exception:
                        break
                    ticks = self._parse_message(message)
                    if ticks:
                        self.on_ticks(self, ticks)

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self.on_error(self, 0, str(exc))
                reconnect_count += 1
                if self.on_reconnect:
                    self.on_reconnect(self, reconnect_count)
                if reconnect_count > 10:
                    break
                import time
                time.sleep(min(reconnect_count * 2, 30))

    def _send_subscribe(self, batch_size: int = 500) -> None:
        if not self._ws or not self._instrument_keys:
            return
        keys = self._instrument_keys
        for start in range(0, len(keys), batch_size):
            batch = keys[start : start + batch_size]
            message = json.dumps({
                "guid": "phase0_sub_%d" % start,
                "method": "sub",
                "data": {
                    "mode": "full",
                    "instrumentKeys": batch,
                },
            })
            try:
                self._ws.send(message)
            except Exception:
                pass
            if start + batch_size < len(keys):
                import time
                time.sleep(0.1)

    def _parse_message(self, message) -> List[Dict]:
        if isinstance(message, bytes):
            return self._parse_binary_message(message)

        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return []

        feeds = data.get("feeds") or {}
        ticks = []
        for instrument_key, feed in feeds.items():
            ff = feed.get("ff") or feed.get("ltpc") or {}
            market_ff = ff.get("marketFF") or ff
            ltpc = ff.get("ltpc") or ff

            depth_data = market_ff.get("marketOHLC") or market_ff.get("depth") or {}
            bid_levels = []
            ask_levels = []
            if "bidAskQuote" in market_ff:
                baq = market_ff["bidAskQuote"]
                for b in baq.get("bids", []):
                    bid_levels.append({"price": b.get("price", 0), "quantity": b.get("quantity", 0), "orders": b.get("orders", 0)})
                for a in baq.get("asks", []):
                    ask_levels.append({"price": a.get("price", 0), "quantity": a.get("quantity", 0), "orders": a.get("orders", 0)})

            tick = {
                "instrument_key": instrument_key,
                "instrument_token": None,
                "last_price": ltpc.get("ltp") or ltpc.get("lastPrice"),
                "volume": market_ff.get("tradedVolume") or market_ff.get("volume"),
                "oi": market_ff.get("oi"),
                "exchange_timestamp": ltpc.get("ltt") or market_ff.get("lastTradeTime"),
                "last_trade_time": ltpc.get("ltt") or market_ff.get("lastTradeTime"),
                "depth": {
                    "buy": bid_levels or [{"price": 0, "quantity": 0, "orders": 0}],
                    "sell": ask_levels or [{"price": 0, "quantity": 0, "orders": 0}],
                },
            }
            ticks.append(tick)
        return ticks

    def _parse_binary_message(self, data: bytes) -> List[Dict]:
        try:
            text = data.decode("utf-8")
            return self._parse_message(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return []
