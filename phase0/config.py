from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    provider: str
    upstox_api_key: str
    upstox_api_secret: str
    upstox_redirect_url: str
    session_state_path: Path
    artifacts_dir: Path
    risk_free_rate: float
    phase0_symbol: str
    spot_instrument_key: str
    derivative_segment: str
    store_raw_json_in_db: bool
    expired_history_months: int
    supabase_db_url: Optional[str]
    # Worker lifecycle
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    seal_lag_seconds: int = 3
    heartbeat_interval_seconds: int = 30
    allow_ltp_fallback: bool = False
    backfill_days: int = 1
    max_dte_days: int = 120
    ws_token_limit: int = 1800

    @property
    def spot_exchange(self) -> str:
        return "NSE"

    @property
    def spot_tradingsymbol(self) -> str:
        return "Nifty 50"


def load_settings() -> Settings:
    provider = _clean_env("PHASE0_PROVIDER") or "upstox"

    api_key = _clean_env("UPSTOX_API_KEY") or ""
    api_secret = _clean_env("UPSTOX_API_SECRET") or ""

    if provider == "upstox" and (not api_key or not api_secret):
        raise RuntimeError("Missing UPSTOX_API_KEY or UPSTOX_API_SECRET in environment.")

    redirect_url = _clean_env("UPSTOX_REDIRECT_URL") or "http://127.0.0.1:8000/callback"
    store_raw = (_clean_env("PHASE0_STORE_RAW_JSON") or "false").lower() in ("true", "1", "yes")

    return Settings(
        provider=provider,
        upstox_api_key=api_key,
        upstox_api_secret=api_secret,
        upstox_redirect_url=redirect_url,
        session_state_path=Path(_clean_env("SESSION_STATE_PATH") or "./state/session.json"),
        artifacts_dir=Path(_clean_env("PHASE0_ARTIFACTS_DIR") or "./artifacts"),
        risk_free_rate=0.06,
        phase0_symbol="NIFTY",
        spot_instrument_key="NSE_INDEX|Nifty 50",
        derivative_segment=_clean_env("PHASE0_DERIVATIVE_SEGMENT") or "NSE_FO",
        store_raw_json_in_db=store_raw,
        expired_history_months=int(_clean_env("PHASE0_EXPIRED_HISTORY_MONTHS") or "6"),
        supabase_db_url=_clean_env("SUPABASE_DB_URL_SESSION"),
    )


def _clean_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip().strip("\"").strip("'")
    return cleaned or None
