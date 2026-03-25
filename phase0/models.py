from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class SessionState:
    access_token: str
    user_id: str
    user_name: str
    provider: str
    email: Optional[str]
    login_time: datetime
    expires_at: datetime


@dataclass
class ProbeUniverseItem:
    role: str
    exchange: str
    tradingsymbol: str
    instrument_key: Optional[str] = None
    instrument_token: Optional[int] = None
    provider: str = "upstox"
    segment: Optional[str] = None
    instrument_type: Optional[str] = None
    expiry: Optional[date] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None
    lot_size: Optional[int] = None

    def quote_symbol(self) -> str:
        if self.instrument_key:
            return self.instrument_key
        return "%s:%s" % (self.exchange, self.tradingsymbol)


@dataclass
class ExpiryNode:
    ts: datetime
    expiry: date
    dte_days: float
    forward: Optional[float]
    atm_strike: Optional[float]
    atm_iv: Optional[float]
    iv_25c: Optional[float]
    iv_25p: Optional[float]
    iv_10c: Optional[float] = None
    iv_10p: Optional[float] = None
    rr25: Optional[float] = None
    bf25: Optional[float] = None
    source_count: int = 0
    quality_score: float = 0.0
    method_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstantMaturityNode:
    ts: datetime
    tenor_code: str
    tenor_days: int
    atm_iv: Optional[float] = None
    iv_25c: Optional[float] = None
    iv_25p: Optional[float] = None
    iv_10c: Optional[float] = None
    iv_10p: Optional[float] = None
    rr25: Optional[float] = None
    bf25: Optional[float] = None
    quality: str = "interpolated"
    bracket_expiries: List[date] = field(default_factory=list)
