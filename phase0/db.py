from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Sequence
from uuid import uuid4

from phase0.artifacts import json_default

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


class Phase0Database:
    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed. Install requirements-phase0.txt to enable DB writes.")
        self.dsn = dsn
        self.conn = None

    def __enter__(self) -> "Phase0Database":
        self.conn = psycopg.connect(self.dsn)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.conn is not None:
            if exc is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.conn.close()
            self.conn = None

    def commit(self) -> None:
        if self.conn is not None:
            self.conn.commit()

    def start_probe_run(self, probe_name: str, started_at: datetime, details: Dict, session_user_id: str = "") -> str:
        run_id = str(uuid4())
        self._execute(
            """
            insert into ops.probe_runs (run_id, probe_name, started_at, status, session_user_id, details_json)
            values (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (run_id, probe_name, started_at, "running", session_user_id or None, self._json(details)),
        )
        return run_id

    def finish_probe_run(self, run_id: str, ended_at: datetime, status: str, details: Dict) -> None:
        self._execute(
            """
            update ops.probe_runs
            set ended_at = %s, status = %s, details_json = %s::jsonb
            where run_id = %s
            """,
            (ended_at, status, self._json(details), run_id),
        )

    def record_probe_event(
        self,
        run_id: str,
        stage: str,
        message: str,
        payload: Dict,
        error_code: str = "",
    ) -> None:
        self._execute(
            """
            insert into ops.probe_errors (run_id, stage, error_code, message, payload_json)
            values (%s, %s, %s, %s, %s::jsonb)
            """,
            (run_id, stage, error_code or None, message, self._json(payload)),
        )

    def upsert_instrument_catalog(self, rows: Sequence[Dict]) -> None:
        sql = """
            insert into market.instrument_catalog (
                as_of_date, provider, provider_instrument_id,
                exchange, segment, tradingsymbol, instrument_token,
                name, instrument_type, expiry, strike, tick_size, lot_size, raw_json
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (as_of_date, exchange, tradingsymbol) do update
            set provider = excluded.provider,
                provider_instrument_id = excluded.provider_instrument_id,
                instrument_token = excluded.instrument_token,
                segment = excluded.segment,
                name = excluded.name,
                instrument_type = excluded.instrument_type,
                expiry = excluded.expiry,
                strike = excluded.strike,
                tick_size = excluded.tick_size,
                lot_size = excluded.lot_size,
                raw_json = excluded.raw_json
        """
        self._executemany(
            sql,
            [
                (
                    row["as_of_date"],
                    row.get("provider", "upstox"),
                    row.get("provider_instrument_id"),
                    row["exchange"],
                    row["segment"],
                    row["tradingsymbol"],
                    row.get("instrument_token"),
                    row["name"],
                    row["instrument_type"],
                    row["expiry"],
                    row["strike"],
                    row.get("tick_size"),
                    row.get("lot_size"),
                    self._json(row.get("raw_json") or {}),
                )
                for row in rows
            ],
        )

    def insert_phase0_universe(self, rows: Sequence[Dict]) -> None:
        sql = """
            insert into ops.phase0_universe (
                run_id, as_of_date, provider, provider_instrument_id,
                role, exchange, tradingsymbol,
                instrument_token, expiry, strike, option_type, meta_json
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        self._executemany(
            sql,
            [
                (
                    row["run_id"],
                    row["as_of_date"],
                    row.get("provider", "upstox"),
                    row.get("provider_instrument_id"),
                    row["role"],
                    row["exchange"],
                    row["tradingsymbol"],
                    row.get("instrument_token"),
                    row["expiry"],
                    row["strike"],
                    row["option_type"],
                    self._json(row["meta_json"]),
                )
                for row in rows
            ],
        )

    def upsert_underlying_snapshots(self, rows: Sequence[Dict]) -> None:
        sql = """
            insert into market.underlying_snapshot_1m (
                ts, source_type, exchange, tradingsymbol, instrument_token,
                instrument_key, provider, last_price, bid, ask, volume, oi,
                quote_quality, raw_json
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (ts, tradingsymbol) do update
            set instrument_token = excluded.instrument_token,
                instrument_key = excluded.instrument_key,
                provider = excluded.provider,
                last_price = excluded.last_price,
                bid = excluded.bid,
                ask = excluded.ask,
                volume = excluded.volume,
                oi = excluded.oi,
                quote_quality = excluded.quote_quality,
                raw_json = excluded.raw_json
        """
        self._executemany(
            sql,
            [
                (
                    row["ts"],
                    row["source_type"],
                    row["exchange"],
                    row["tradingsymbol"],
                    row.get("instrument_token"),
                    row.get("instrument_key"),
                    row.get("provider", "upstox"),
                    row["last_price"],
                    row["bid"],
                    row["ask"],
                    row["volume"],
                    row["oi"],
                    row["quote_quality"],
                    self._json(row.get("raw_json") or {}),
                )
                for row in rows
            ],
        )

    def upsert_option_snapshots(self, rows: Sequence[Dict]) -> None:
        sql = """
            insert into market.option_snapshot_1m (
                ts, exchange, tradingsymbol, instrument_token, instrument_key,
                provider, expiry, strike, option_type, bid, ask, ltp,
                bid_qty, ask_qty, volume, oi, quote_quality, last_trade_time, raw_json
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (ts, tradingsymbol) do update
            set instrument_token = excluded.instrument_token,
                instrument_key = excluded.instrument_key,
                provider = excluded.provider,
                bid = excluded.bid,
                ask = excluded.ask,
                ltp = excluded.ltp,
                bid_qty = excluded.bid_qty,
                ask_qty = excluded.ask_qty,
                volume = excluded.volume,
                oi = excluded.oi,
                quote_quality = excluded.quote_quality,
                last_trade_time = excluded.last_trade_time,
                raw_json = excluded.raw_json
        """
        self._executemany(
            sql,
            [
                (
                    row["ts"],
                    row["exchange"],
                    row["tradingsymbol"],
                    row.get("instrument_token"),
                    row.get("instrument_key"),
                    row.get("provider", "upstox"),
                    row["expiry"],
                    row["strike"],
                    row["option_type"],
                    row["bid"],
                    row["ask"],
                    row["ltp"],
                    row["bid_qty"],
                    row["ask_qty"],
                    row["volume"],
                    row["oi"],
                    row["quote_quality"],
                    row["last_trade_time"],
                    self._json(row.get("raw_json") or {}),
                )
                for row in rows
            ],
        )

    def upsert_expiry_nodes(self, rows: Sequence[Dict]) -> None:
        sql = """
            insert into analytics.expiry_nodes_1m (
                ts, expiry, dte_days, forward, atm_strike, atm_iv, iv_25c, iv_25p,
                rr25, bf25, source_count, quality_score, provider, source_mode,
                method_json
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (ts, expiry) do update
            set dte_days = excluded.dte_days,
                forward = excluded.forward,
                atm_strike = excluded.atm_strike,
                atm_iv = excluded.atm_iv,
                iv_25c = excluded.iv_25c,
                iv_25p = excluded.iv_25p,
                rr25 = excluded.rr25,
                bf25 = excluded.bf25,
                source_count = excluded.source_count,
                quality_score = excluded.quality_score,
                provider = excluded.provider,
                source_mode = excluded.source_mode,
                method_json = excluded.method_json
        """
        self._executemany(
            sql,
            [
                (
                    row["ts"],
                    row["expiry"],
                    row["dte_days"],
                    row["forward"],
                    row["atm_strike"],
                    row["atm_iv"],
                    row["iv_25c"],
                    row["iv_25p"],
                    row["rr25"],
                    row["bf25"],
                    row["source_count"],
                    row["quality_score"],
                    row.get("provider", "upstox"),
                    row.get("source_mode", "live_quote"),
                    self._json(row.get("method_json") or {}),
                )
                for row in rows
            ],
        )

    def _execute(self, sql: str, params: Sequence) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)

    def _executemany(self, sql: str, params: Sequence[Sequence]) -> None:
        if not params:
            return
        with self.conn.cursor() as cursor:
            cursor.executemany(sql, params)

    def _json(self, payload: Dict) -> str:
        return json.dumps(payload, default=json_default)
