CREATE TABLE IF NOT EXISTS ops.history_backfill_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_date date NOT NULL,
    to_date date NOT NULL,
    daily_source text NOT NULL,
    skip_db boolean NOT NULL DEFAULT false,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'partial', 'failed')),
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz
);

CREATE TABLE IF NOT EXISTS ops.history_backfill_day_log (
    run_id uuid NOT NULL REFERENCES ops.history_backfill_run (id) ON DELETE CASCADE,
    trade_date date NOT NULL,
    mode text NOT NULL CHECK (mode IN ('full', 'daily')),
    source text NOT NULL,
    status text NOT NULL CHECK (
        status IN (
            'completed',
            'partial',
            'no_data',
            'unsupported_legacy_format',
            'download_error',
            'parse_error',
            'source_error'
        )
    ),
    persisted boolean NOT NULL DEFAULT false,
    skip_db boolean NOT NULL DEFAULT false,
    elapsed_sec numeric(12, 3) NOT NULL DEFAULT 0,
    row_counts_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    outputs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    diagnostics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    message text,
    artifact_path text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, trade_date)
);

CREATE INDEX IF NOT EXISTS history_backfill_run_started_idx
    ON ops.history_backfill_run (started_at DESC);

CREATE INDEX IF NOT EXISTS history_backfill_day_status_idx
    ON ops.history_backfill_day_log (status, trade_date DESC);
