-- Phase 1: derived metrics tables, worker ops, product-facing tables
-- Raw option/underlying snapshots NOT stored in Supabase (storage savings)

-- ============================================================
-- Extend existing tables
-- ============================================================

ALTER TABLE analytics.expiry_nodes_1m
  ADD COLUMN IF NOT EXISTS iv_10c numeric(10, 6),
  ADD COLUMN IF NOT EXISTS iv_10p numeric(10, 6);

-- ============================================================
-- analytics schema: internal derived data
-- ============================================================

CREATE TABLE IF NOT EXISTS analytics.constant_maturity_nodes_1m (
    ts timestamptz NOT NULL,
    tenor_code text NOT NULL,
    tenor_days integer NOT NULL,
    atm_iv numeric(10, 6),
    iv_25c numeric(10, 6),
    iv_25p numeric(10, 6),
    iv_10c numeric(10, 6),
    iv_10p numeric(10, 6),
    rr25 numeric(10, 6),
    bf25 numeric(10, 6),
    quality text NOT NULL DEFAULT 'interpolated',
    bracket_expiries_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_mode text NOT NULL DEFAULT 'live',
    provider text NOT NULL DEFAULT 'upstox',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ts, tenor_code)
);

CREATE INDEX IF NOT EXISTS cm_nodes_tenor_ts_idx
    ON analytics.constant_maturity_nodes_1m (tenor_code, ts DESC);

CREATE TABLE IF NOT EXISTS analytics.metric_baselines_daily (
    metric_date date NOT NULL,
    metric_key text NOT NULL,
    close_value numeric(14, 6),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (metric_date, metric_key)
);

CREATE TABLE IF NOT EXISTS analytics.flow_baselines (
    metric_date date NOT NULL,
    metric_key text NOT NULL,
    window_code text NOT NULL,
    change_value numeric(14, 6),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (metric_date, metric_key, window_code)
);

-- ============================================================
-- public schema: browser-readable product tables
-- ============================================================

CREATE TABLE IF NOT EXISTS public.metric_series_1m (
    ts timestamptz NOT NULL,
    metric_key text NOT NULL,
    tenor_code text,
    window_code text,
    value numeric(14, 6),
    percentile numeric(6, 1),
    provisional boolean NOT NULL DEFAULT true,
    source_mode text NOT NULL DEFAULT 'live',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ts, metric_key)
);

CREATE INDEX IF NOT EXISTS metric_series_key_ts_idx
    ON public.metric_series_1m (metric_key, ts DESC);

CREATE INDEX IF NOT EXISTS metric_series_ts_idx
    ON public.metric_series_1m (ts DESC);

CREATE TABLE IF NOT EXISTS public.surface_cells_current (
    tenor_code text NOT NULL,
    delta_bucket text NOT NULL,
    as_of timestamptz NOT NULL,
    iv numeric(10, 6),
    iv_percentile numeric(6, 1),
    quality_score numeric(6, 3),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenor_code, delta_bucket)
);

CREATE TABLE IF NOT EXISTS public.dashboard_current (
    id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    as_of timestamptz NOT NULL DEFAULT now(),
    state_score numeric(6, 1),
    stress_score numeric(6, 1),
    quadrant text,
    key_cards_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    insight_bullets_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    scenario_implications_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    data_quality_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Seed the singleton row
INSERT INTO public.dashboard_current (id, as_of)
VALUES (1, now())
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.daily_brief_history (
    brief_date date PRIMARY KEY,
    generated_at timestamptz NOT NULL DEFAULT now(),
    quadrant text,
    state_score numeric(6, 1),
    stress_score numeric(6, 1),
    headline text NOT NULL DEFAULT '',
    body_text text NOT NULL DEFAULT '',
    key_metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_quality_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- ops schema: worker operations
-- ============================================================

CREATE TABLE IF NOT EXISTS ops.worker_heartbeat (
    worker_id text PRIMARY KEY,
    phase text NOT NULL CHECK (phase IN (
        'startup', 'pre_market', 'market_hours', 'post_market', 'idle', 'error'
    )),
    last_ts timestamptz,
    last_minute_sealed timestamptz,
    status text NOT NULL DEFAULT 'running',
    error_message text,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.gap_fill_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gap_start_ts timestamptz NOT NULL,
    gap_end_ts timestamptz NOT NULL,
    gap_type text NOT NULL CHECK (gap_type IN ('full_day', 'intraday')),
    status text NOT NULL CHECK (status IN (
        'pending', 'filling', 'completed', 'partial', 'unfillable'
    )),
    minutes_expected integer,
    minutes_filled integer DEFAULT 0,
    attempt_count integer NOT NULL DEFAULT 0,
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gap_fill_log_status_idx
    ON ops.gap_fill_log (status, gap_start_ts);

-- ============================================================
-- RLS policies: public tables readable by authenticated users
-- ============================================================

ALTER TABLE public.metric_series_1m ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.surface_cells_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashboard_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_brief_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read metric_series"
    ON public.metric_series_1m FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read surface_cells"
    ON public.surface_cells_current FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read dashboard"
    ON public.dashboard_current FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read daily_brief"
    ON public.daily_brief_history FOR SELECT TO authenticated USING (true);
