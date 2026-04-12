"""CLI entry point for the daily AI-generated regime narrative.

Invoked by the GitHub Actions `Daily Pipeline` workflow AFTER the existing
backfill step has written today's EOD snapshot to Supabase.

Behaviour:
  * Reads today's dashboard state + 7-day regime trail from Supabase.
  * Calls the configured LLM provider (Google AI Studio / Anthropic / OpenAI /
    Groq) via pydantic-ai, with a strict Pydantic output schema.
  * Writes the accepted narrative to `dashboard_current` + `daily_brief_history`
    (only on success; never clobbers a good narrative with NULL).
  * ALWAYS writes an audit row to `narrative_runs` — success or failure.
  * Exits 0 on all "expected" failure modes (missing key, rate limit, guardrail
    rejection) so the pipeline stays green. Only uncaught bugs cause a non-zero
    exit.

Run locally:
    GEMINI_API_KEY=... NARRATIVE_PROVIDER=google-gla NARRATIVE_MODEL=gemma-4-31b-it \\
        SUPABASE_DB_URL_SESSION=... python -m worker.narrative_job
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from typing import Optional

from phase0.config import Settings, load_settings
from phase0.time_utils import indian_timezone
from worker.db import WorkerDatabase
from worker.narrative import (
    build_context,
    generate_narrative,
    log_narrative_run,
    upsert_narrative,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("worker.narrative_job")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the daily regime narrative.")
    parser.add_argument(
        "--date",
        help="Target brief_date (YYYY-MM-DD). Defaults to today in IST.",
        default=None,
    )
    args = parser.parse_args()

    # 1. Settings / feature flag.
    settings = load_settings()
    if not settings.narrative_enabled:
        log.info("NARRATIVE_ENABLED is false; skipping narrative generation.")
        return 0

    if not settings.supabase_db_url:
        log.warning("SUPABASE_DB_URL_SESSION is not set; cannot read/write narrative.")
        return 0

    # 2. Resolve target date (IST).
    brief_date = _resolve_brief_date(args.date)
    log.info("Generating narrative for brief_date=%s", brief_date)

    # 3. Do the work.
    try:
        _run(settings, brief_date)
    except Exception as e:
        # Anything unexpected — we still log it but exit 0 to match the
        # workflow's `continue-on-error: true` posture (the prior daily
        # pipeline step has already written EOD data; narrative is non-fatal).
        log.error("Narrative job failed unexpectedly: %s", e, exc_info=True)
        return 0

    return 0


def _run(settings: Settings, brief_date: date) -> None:
    with WorkerDatabase(settings.supabase_db_url) as db:
        assert db.conn is not None

        # 1. Build context (pure SELECTs, no writes).
        ctx = build_context(db.conn, brief_date=brief_date)
        log.info(
            "Context built: quadrant=%s state=%s stress=%s grid=%d composite=%d flows=%d trail=%d",
            ctx.quadrant, ctx.state_score, ctx.stress_score,
            len(ctx.grid_metrics), len(ctx.composite_metrics),
            len(ctx.flow_metrics), len(ctx.trail),
        )

        # 2. Call the LLM. Never raises on known failure modes.
        result = generate_narrative(ctx, settings)

        # 3. ALWAYS write an audit row (success and failure alike).
        try:
            log_narrative_run(db.conn, brief_date, ctx, result)
        except Exception as e:
            # If even the audit insert fails, log loudly — something
            # structural is wrong. Still don't crash the pipeline.
            log.error("Failed to insert narrative_runs row: %s", e, exc_info=True)

        # 4. Only on success, update user-facing tables.
        if result.succeeded and result.narrative is not None:
            try:
                upsert_narrative(db.conn, brief_date, result.narrative, result.model)
                log.info(
                    "Narrative upserted: model=%s chars=%d (dashboard_current + daily_brief_history)",
                    result.model, len(result.narrative),
                )
            except Exception as e:
                log.error("Failed to upsert narrative to user tables: %s", e, exc_info=True)
        else:
            log.warning(
                "Narrative not persisted (error=%s guardrail=%s). Previous narrative intact.",
                result.api_error, result.guardrail_error,
            )


def _resolve_brief_date(date_arg: Optional[str]) -> date:
    if date_arg:
        return datetime.strptime(date_arg, "%Y-%m-%d").date()
    ist = indian_timezone()
    return datetime.now(tz=ist).date()


if __name__ == "__main__":
    sys.exit(main())
