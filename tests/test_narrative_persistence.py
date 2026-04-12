"""Tests for narrative persistence — audit log + user-facing upsert.

Uses mocked psycopg connections. Verifies:
  * log_narrative_run always runs (success path + error path).
  * upsert_narrative updates BOTH dashboard_current and daily_brief_history.
  * Empty narrative is refused by upsert_narrative (defensive no-op).
"""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock

from worker.narrative.context import NarrativeContext
from worker.narrative.generator import GenerationResult
from worker.narrative.persistence import log_narrative_run, upsert_narrative


class _TrackingCursor:
    """Minimal psycopg cursor stub that records every execute() call."""

    def __init__(self):
        self.executed: list[str] = []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _conn():
    """Return (conn, cursor) — the same cursor is reused across every
    `with conn.cursor()` so tests can inspect the full execute history."""
    cur = _TrackingCursor()
    conn = MagicMock()
    conn.cursor.side_effect = lambda: cur
    # expose the cursor for the test to inspect
    conn._tracking_cursor = cur
    return conn


def _ctx() -> NarrativeContext:
    return NarrativeContext(
        brief_date=date(2026, 4, 12),
        quadrant="Stress",
        state_score=57.3,
        stress_score=28.1,
    )


class TestLogNarrativeRun(unittest.TestCase):
    def test_successful_run_is_inserted(self):
        conn = _conn()
        result = GenerationResult(
            narrative="Stress regime persists as vol holds near extremes.",
            provider="google-gla",
            model="gemma-4-31b-it",
            prompt_tokens=500,
            completion_tokens=80,
            latency_ms=1240,
        )

        log_narrative_run(conn, date(2026, 4, 12), _ctx(), result)

        executed = conn._tracking_cursor.executed
        self.assertTrue(
            any("INSERT INTO public.narrative_runs" in sql for sql in executed),
            f"expected INSERT call, got: {executed}",
        )

    def test_failed_run_is_still_logged(self):
        conn = _conn()
        result = GenerationResult(
            narrative=None,
            provider="google-gla",
            model="gemma-4-31b-it",
            api_error="timeout",
        )

        log_narrative_run(conn, date(2026, 4, 12), _ctx(), result)

        executed = conn._tracking_cursor.executed
        self.assertTrue(any("INSERT INTO public.narrative_runs" in sql for sql in executed))


class TestUpsertNarrative(unittest.TestCase):
    def test_both_tables_updated(self):
        conn = _conn()
        upsert_narrative(
            conn,
            brief_date=date(2026, 4, 12),
            narrative="Stress regime persists as vol holds near extremes.",
            model="gemma-4-31b-it",
        )

        executed = conn._tracking_cursor.executed
        self.assertTrue(
            any("UPDATE public.dashboard_current" in sql for sql in executed),
            f"expected dashboard UPDATE; got: {executed}",
        )
        self.assertTrue(
            any("UPDATE public.daily_brief_history" in sql for sql in executed),
            f"expected history UPDATE; got: {executed}",
        )

    def test_empty_narrative_refused(self):
        conn = _conn()
        upsert_narrative(
            conn,
            brief_date=date(2026, 4, 12),
            narrative="",
            model="gemma-4-31b-it",
        )

        executed = conn._tracking_cursor.executed
        self.assertFalse(
            any("UPDATE" in sql for sql in executed),
            f"expected no UPDATE for empty narrative; got: {executed}",
        )


if __name__ == "__main__":
    unittest.main()
