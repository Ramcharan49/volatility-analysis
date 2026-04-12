-- ============================================================
-- Regime narrative: AI-generated daily paragraph + audit trail.
-- All changes are additive and nullable; existing reads/writes
-- are untouched. New rows default the added columns to NULL.
-- ============================================================

-- 1. dashboard_current (singleton) — narrative columns.
ALTER TABLE public.dashboard_current
    ADD COLUMN IF NOT EXISTS regime_narrative       text,
    ADD COLUMN IF NOT EXISTS narrative_generated_at timestamptz,
    ADD COLUMN IF NOT EXISTS narrative_model        text;

-- 2. daily_brief_history (one row per trading day) — mirror narrative columns.
ALTER TABLE public.daily_brief_history
    ADD COLUMN IF NOT EXISTS regime_narrative       text,
    ADD COLUMN IF NOT EXISTS narrative_generated_at timestamptz,
    ADD COLUMN IF NOT EXISTS narrative_model        text;

-- 3. narrative_runs — per-call audit log for A/B comparison.
--    Isolated, no FKs, no references from existing schema.
CREATE TABLE IF NOT EXISTS public.narrative_runs (
    id                bigserial PRIMARY KEY,
    brief_date        date NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT now(),
    provider          text NOT NULL,
    model             text NOT NULL,
    narrative         text,
    prompt_tokens     integer,
    completion_tokens integer,
    latency_ms        integer,
    cost_usd          numeric(10, 6),
    guardrail_error   text,
    api_error         text,
    context_json      jsonb
);

CREATE INDEX IF NOT EXISTS narrative_runs_brief_date_model_idx
    ON public.narrative_runs (brief_date, model);
