"""DB writes for narrative results.

Two functions:
  * `log_narrative_run()` — ALWAYS invoked, once per LLM call. Writes to
    `public.narrative_runs` (the audit table) regardless of success/failure.
  * `upsert_narrative()` — ONLY invoked on success. Updates
    `public.dashboard_current` (singleton) and `public.daily_brief_history`
    for today's brief_date so the FE picks up the new paragraph.

Never writes NULL to `dashboard_current.regime_narrative` — we prefer stale
but valid over freshly-null.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Optional

from phase0.artifacts import json_default

from .context import NarrativeContext
from .generator import GenerationResult


log = logging.getLogger("worker.narrative")


def log_narrative_run(
    conn,
    brief_date: date,
    ctx: NarrativeContext,
    result: GenerationResult,
) -> None:
    """Append one row to `public.narrative_runs`. Always called, whether the
    generation succeeded or failed, so we can A/B-compare over time."""
    sql = """
        INSERT INTO public.narrative_runs (
            brief_date, generated_at, provider, model,
            narrative, prompt_tokens, completion_tokens, latency_ms,
            guardrail_error, api_error, context_json
        )
        VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            brief_date,
            result.provider,
            result.model,
            result.narrative,
            result.prompt_tokens,
            result.completion_tokens,
            result.latency_ms,
            result.guardrail_error,
            result.api_error,
            _json(_context_to_jsonable(ctx)),
        ))


def upsert_narrative(
    conn,
    brief_date: date,
    narrative: str,
    model: str,
) -> None:
    """Write the accepted narrative to both user-facing tables.

    Runs in a single transaction (the caller commits). Only invoked when the
    narrative passed all guardrails — we do not overwrite a prior day's good
    narrative with NULL.
    """
    if not narrative:
        log.warning("upsert_narrative called with empty narrative; ignoring.")
        return

    dash_sql = """
        UPDATE public.dashboard_current
        SET regime_narrative       = %s,
            narrative_generated_at = now(),
            narrative_model        = %s
        WHERE id = 1
    """

    history_sql = """
        UPDATE public.daily_brief_history
        SET regime_narrative       = %s,
            narrative_generated_at = now(),
            narrative_model        = %s
        WHERE brief_date = %s
    """

    with conn.cursor() as cur:
        cur.execute(dash_sql, (narrative, model))
        cur.execute(history_sql, (narrative, model, brief_date))


# ── Internals ────────────────────────────────────────────────────────────

def _context_to_jsonable(ctx: NarrativeContext) -> dict:
    """Serialise a NarrativeContext for the audit `context_json` column.

    We manually walk the dataclasses (instead of using asdict blindly) so the
    JSON is small, readable in Supabase, and stable across refactors."""
    return {
        "brief_date": ctx.brief_date.isoformat(),
        "quadrant": ctx.quadrant,
        "state_score": ctx.state_score,
        "stress_score": ctx.stress_score,
        "grid_metrics": [asdict(m) for m in ctx.grid_metrics],
        "composite_metrics": [asdict(m) for m in ctx.composite_metrics],
        "flow_metrics": [asdict(f) for f in ctx.flow_metrics],
        "trail": [
            {
                "day": t.day.isoformat(),
                "state_score": t.state_score,
                "stress_score": t.stress_score,
                "quadrant": t.quadrant,
            }
            for t in ctx.trail
        ],
    }


def _json(payload) -> str:
    return json.dumps(payload, default=json_default)
