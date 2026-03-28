"""DB layer for V1 worker tables.

Handles upserts for constant-maturity nodes, metric series, surface cells,
dashboard, heartbeat, and baselines. Follows the same patterns as phase0/db.py.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from phase0.artifacts import json_default

try:
    import psycopg
except ImportError:
    psycopg = None


class WorkerDatabase:
    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed.")
        self.dsn = dsn
        self.conn = None

    def __enter__(self) -> "WorkerDatabase":
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

    # ── Expiry nodes (extended with iv_10c/iv_10p) ─────────────────

    def upsert_expiry_nodes(self, rows: Sequence[Dict], source_mode: str = "live") -> None:
        sql = """
            INSERT INTO analytics.expiry_nodes_1m (
                ts, expiry, dte_days, forward, atm_strike, atm_iv,
                iv_25c, iv_25p, iv_10c, iv_10p,
                rr25, bf25, source_count, quality_score,
                provider, source_mode, method_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (ts, expiry) DO UPDATE
            SET dte_days = excluded.dte_days,
                forward = excluded.forward,
                atm_strike = excluded.atm_strike,
                atm_iv = excluded.atm_iv,
                iv_25c = excluded.iv_25c,
                iv_25p = excluded.iv_25p,
                iv_10c = excluded.iv_10c,
                iv_10p = excluded.iv_10p,
                rr25 = excluded.rr25,
                bf25 = excluded.bf25,
                source_count = excluded.source_count,
                quality_score = excluded.quality_score,
                provider = excluded.provider,
                source_mode = excluded.source_mode,
                method_json = excluded.method_json
            WHERE analytics.expiry_nodes_1m.source_mode IS DISTINCT FROM 'live'
               OR excluded.source_mode = 'live'
        """
        self._executemany(sql, [
            (
                row["ts"], row["expiry"], row["dte_days"], row["forward"],
                row["atm_strike"], row["atm_iv"], row["iv_25c"], row["iv_25p"],
                row.get("iv_10c"), row.get("iv_10p"),
                row["rr25"], row["bf25"], row["source_count"], row["quality_score"],
                row.get("provider", "upstox"), source_mode,
                self._json(row.get("method_json") or {}),
            )
            for row in rows
        ])

    # ── Constant-maturity nodes ────────────────────────────────────

    def upsert_cm_nodes(self, rows: Sequence[Dict], source_mode: str = "live") -> None:
        sql = """
            INSERT INTO analytics.constant_maturity_nodes_1m (
                ts, tenor_code, tenor_days, atm_iv, iv_25c, iv_25p,
                iv_10c, iv_10p, rr25, bf25, quality,
                bracket_expiries_json, source_mode, provider
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (ts, tenor_code) DO UPDATE
            SET tenor_days = excluded.tenor_days,
                atm_iv = excluded.atm_iv,
                iv_25c = excluded.iv_25c,
                iv_25p = excluded.iv_25p,
                iv_10c = excluded.iv_10c,
                iv_10p = excluded.iv_10p,
                rr25 = excluded.rr25,
                bf25 = excluded.bf25,
                quality = excluded.quality,
                bracket_expiries_json = excluded.bracket_expiries_json,
                source_mode = excluded.source_mode,
                provider = excluded.provider
            WHERE analytics.constant_maturity_nodes_1m.source_mode IS DISTINCT FROM 'live'
               OR excluded.source_mode = 'live'
        """
        self._executemany(sql, [
            (
                row["ts"], row["tenor_code"], row["tenor_days"],
                row.get("atm_iv"), row.get("iv_25c"), row.get("iv_25p"),
                row.get("iv_10c"), row.get("iv_10p"),
                row.get("rr25"), row.get("bf25"),
                row.get("quality", "interpolated"),
                self._json(row.get("bracket_expiries", [])),
                source_mode, row.get("provider", "upstox"),
            )
            for row in rows
        ])

    # ── Metric series ─────────────────────────────────────────────

    def upsert_metric_series(self, rows: Sequence[Dict], source_mode: str = "live") -> None:
        sql = """
            INSERT INTO public.metric_series_1m (
                ts, metric_key, tenor_code, window_code, value,
                percentile, provisional, source_mode
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ts, metric_key) DO UPDATE
            SET tenor_code = excluded.tenor_code,
                window_code = excluded.window_code,
                value = excluded.value,
                percentile = excluded.percentile,
                provisional = excluded.provisional,
                source_mode = excluded.source_mode
            WHERE public.metric_series_1m.source_mode IS DISTINCT FROM 'live'
               OR excluded.source_mode = 'live'
        """
        self._executemany(sql, [
            (
                row["ts"], row["metric_key"],
                row.get("tenor_code"), row.get("window_code"),
                row.get("value"), row.get("percentile"),
                row.get("provisional", True), source_mode,
            )
            for row in rows
        ])

    # ── Surface cells ─────────────────────────────────────────────

    def upsert_surface_cells(self, cells: Sequence[Dict]) -> None:
        sql = """
            INSERT INTO public.surface_cells_current (
                tenor_code, delta_bucket, as_of, iv, iv_percentile, quality_score
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenor_code, delta_bucket) DO UPDATE
            SET as_of = excluded.as_of,
                iv = excluded.iv,
                iv_percentile = excluded.iv_percentile,
                quality_score = excluded.quality_score
        """
        self._executemany(sql, [
            (
                c["tenor_code"], c["delta_bucket"], c["as_of"],
                c.get("iv"), c.get("iv_percentile"), c.get("quality_score", 0.0),
            )
            for c in cells
        ])

    # ── Dashboard singleton ───────────────────────────────────────

    def upsert_dashboard(self, data: Dict) -> None:
        sql = """
            UPDATE public.dashboard_current
            SET as_of = %s,
                state_score = %s,
                stress_score = %s,
                quadrant = %s,
                key_cards_json = %s::jsonb,
                insight_bullets_json = %s::jsonb,
                scenario_implications_json = %s::jsonb,
                data_quality_json = %s::jsonb,
                updated_at = now()
            WHERE id = 1
        """
        self._execute(sql, (
            data["as_of"],
            data.get("state_score"),
            data.get("stress_score"),
            data.get("quadrant"),
            self._json(data.get("key_cards", [])),
            self._json(data.get("insight_bullets", [])),
            self._json(data.get("scenario_implications", [])),
            self._json(data.get("data_quality", {})),
        ))

    # ── Worker heartbeat ──────────────────────────────────────────

    def upsert_heartbeat(self, worker_id: str, phase: str, last_ts: Optional[datetime],
                         last_minute_sealed: Optional[datetime], status: str = "running",
                         error_message: Optional[str] = None, details: Optional[Dict] = None) -> None:
        sql = """
            INSERT INTO ops.worker_heartbeat (
                worker_id, phase, last_ts, last_minute_sealed,
                status, error_message, details_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
            ON CONFLICT (worker_id) DO UPDATE
            SET phase = excluded.phase,
                last_ts = excluded.last_ts,
                last_minute_sealed = excluded.last_minute_sealed,
                status = excluded.status,
                error_message = excluded.error_message,
                details_json = excluded.details_json,
                updated_at = now()
        """
        self._execute(sql, (
            worker_id, phase, last_ts, last_minute_sealed,
            status, error_message, self._json(details or {}),
        ))

    # ── Baselines ─────────────────────────────────────────────────

    def upsert_metric_baselines(self, rows: Sequence[Dict]) -> None:
        sql = """
            INSERT INTO analytics.metric_baselines_daily (metric_date, metric_key, close_value)
            VALUES (%s, %s, %s)
            ON CONFLICT (metric_date, metric_key) DO UPDATE
            SET close_value = excluded.close_value
        """
        self._executemany(sql, [
            (row["metric_date"], row["metric_key"], row["close_value"])
            for row in rows
        ])

    def upsert_flow_baselines(self, rows: Sequence[Dict]) -> None:
        sql = """
            INSERT INTO analytics.flow_baselines (metric_date, metric_key, window_code, change_value)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (metric_date, metric_key, window_code) DO UPDATE
            SET change_value = excluded.change_value
        """
        self._executemany(sql, [
            (row["metric_date"], row["metric_key"], row["window_code"], row["change_value"])
            for row in rows
        ])

    # ── Daily brief ───────────────────────────────────────────────

    def upsert_daily_brief(self, data: Dict) -> None:
        sql = """
            INSERT INTO public.daily_brief_history (
                brief_date, generated_at, quadrant, state_score, stress_score,
                headline, body_text, key_metrics_json, data_quality_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (brief_date) DO UPDATE
            SET generated_at = excluded.generated_at,
                quadrant = excluded.quadrant,
                state_score = excluded.state_score,
                stress_score = excluded.stress_score,
                headline = excluded.headline,
                body_text = excluded.body_text,
                key_metrics_json = excluded.key_metrics_json,
                data_quality_json = excluded.data_quality_json
        """
        self._execute(sql, (
            data["brief_date"], data.get("generated_at", datetime.now()),
            data.get("quadrant"), data.get("state_score"), data.get("stress_score"),
            data.get("headline", ""), data.get("body_text", ""),
            self._json(data.get("key_metrics", {})),
            self._json(data.get("data_quality", {})),
        ))

    # ── Queries ───────────────────────────────────────────────────

    def fetch_latest_metric_values(self, metric_keys: Sequence[str], lookback_minutes: int,
                                   ref_ts: datetime) -> Dict[str, List[Dict]]:
        """Fetch recent metric_series rows for flow metric seeding."""
        sql = """
            SELECT ts, metric_key, value
            FROM public.metric_series_1m
            WHERE metric_key = ANY(%s)
              AND ts >= %s
              AND ts <= %s
            ORDER BY metric_key, ts
        """
        start_ts = ref_ts - timedelta(minutes=lookback_minutes)
        result: Dict[str, List[Dict]] = {k: [] for k in metric_keys}
        with self.conn.cursor() as cur:
            cur.execute(sql, (list(metric_keys), start_ts, ref_ts))
            for row in cur.fetchall():
                result.setdefault(row[1], []).append({"ts": row[0], "value": row[2]})
        return result

    def fetch_metric_baselines(self, lookback_days: int = 252) -> Dict[str, List[float]]:
        """Load daily-close baselines for percentile computation."""
        sql = """
            SELECT metric_key, close_value
            FROM analytics.metric_baselines_daily
            WHERE metric_date >= %s
            ORDER BY metric_key, metric_date
        """
        cutoff = date.today() - timedelta(days=lookback_days)
        result: Dict[str, List[float]] = {}
        with self.conn.cursor() as cur:
            cur.execute(sql, (cutoff,))
            for row in cur.fetchall():
                result.setdefault(row[0], []).append(float(row[1]) if row[1] is not None else None)
        return result

    def fetch_flow_baselines(self, lookback_days: int = 252) -> Dict[str, List[float]]:
        """Load historical flow changes for flow percentile computation."""
        sql = """
            SELECT 'd_' || metric_key || '_' || window_code AS flow_key, change_value
            FROM analytics.flow_baselines
            WHERE metric_date >= %s
            ORDER BY metric_key, window_code, metric_date
        """
        cutoff = date.today() - timedelta(days=lookback_days)
        result: Dict[str, List[float]] = {}
        with self.conn.cursor() as cur:
            cur.execute(sql, (cutoff,))
            for row in cur.fetchall():
                result.setdefault(row[0], []).append(float(row[1]) if row[1] is not None else None)
        return result

    def fetch_last_minute_metrics(self, day: date) -> Dict[str, float]:
        """Fetch the most recent metric values for a given trading day."""
        sql = """
            SELECT metric_key, value
            FROM public.metric_series_1m
            WHERE ts = (SELECT max(ts) FROM public.metric_series_1m WHERE ts::date = %s)
        """
        result: Dict[str, float] = {}
        with self.conn.cursor() as cur:
            cur.execute(sql, (day,))
            for row in cur.fetchall():
                if row[1] is not None:
                    result[row[0]] = float(row[1])
        return result

    def fetch_last_sealed_ts(self) -> Optional[datetime]:
        """Get the most recent ts from expiry_nodes_1m."""
        sql = "SELECT max(ts) FROM analytics.expiry_nodes_1m"
        with self.conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None

    # ── Gap fill log ─────────────────────────────────────────────

    def insert_gap_fill_log(self, gap_start_ts: datetime, gap_end_ts: datetime,
                            gap_type: str, minutes_expected: int) -> str:
        """Insert a gap_fill_log row with status='filling'. Returns UUID string."""
        sql = """
            INSERT INTO ops.gap_fill_log (gap_start_ts, gap_end_ts, gap_type, status,
                minutes_expected, attempt_count, started_at)
            VALUES (%s, %s, %s, 'filling', %s, 1, now())
            RETURNING id::text
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (gap_start_ts, gap_end_ts, gap_type, minutes_expected))
            row = cur.fetchone()
            return row[0]

    def update_gap_fill_log(self, log_id: str, status: str, minutes_filled: int,
                            error_message: Optional[str] = None) -> None:
        """Update gap_fill_log status to completed/partial/unfillable."""
        sql = """
            UPDATE ops.gap_fill_log
            SET status = %s, minutes_filled = %s, error_message = %s,
                completed_at = now()
            WHERE id = %s::uuid
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (status, minutes_filled, error_message, log_id))

    # ── Internals ─────────────────────────────────────────────────

    def _execute(self, sql: str, params: Sequence) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)

    def _executemany(self, sql: str, params: Sequence[Sequence]) -> None:
        if not params:
            return
        with self.conn.cursor() as cursor:
            cursor.executemany(sql, params)

    def _json(self, payload: Any) -> str:
        return json.dumps(payload, default=json_default)
