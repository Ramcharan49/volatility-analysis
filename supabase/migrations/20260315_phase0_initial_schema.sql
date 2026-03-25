create extension if not exists pgcrypto;
create extension if not exists pg_cron;

create schema if not exists market;
create schema if not exists analytics;
create schema if not exists ops;

create table if not exists market.instrument_catalog (
    id uuid primary key default gen_random_uuid(),
    as_of_date date not null,
    exchange text not null,
    segment text not null,
    tradingsymbol text not null,
    instrument_token bigint not null,
    name text,
    instrument_type text,
    expiry date,
    strike numeric(12, 2),
    tick_size numeric(12, 6),
    lot_size integer,
    raw_json jsonb not null,
    created_at timestamptz not null default now(),
    unique (as_of_date, exchange, tradingsymbol)
);

create index if not exists instrument_catalog_as_of_segment_idx
    on market.instrument_catalog (as_of_date, segment, name);

create index if not exists instrument_catalog_token_idx
    on market.instrument_catalog (instrument_token);

create table if not exists ops.probe_runs (
    run_id uuid primary key default gen_random_uuid(),
    probe_name text not null,
    started_at timestamptz not null,
    ended_at timestamptz,
    status text not null check (status in ('running', 'completed', 'failed')),
    session_user_id text,
    details_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists ops.probe_errors (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references ops.probe_runs (run_id) on delete cascade,
    stage text not null check (
        stage in (
            'session_load',
            'profile_check',
            'instrument_sync',
            'quote_fetch',
            'historical_fetch',
            'quant_compute',
            'db_write',
            'websocket_connect',
            'websocket_reconnect',
            'minute_seal',
            'replay'
        )
    ),
    error_code text,
    message text not null,
    payload_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists probe_errors_run_created_idx
    on ops.probe_errors (run_id, created_at desc);

create table if not exists ops.phase0_universe (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references ops.probe_runs (run_id) on delete cascade,
    as_of_date date not null,
    role text not null check (role in ('spot', 'future_front', 'future_next', 'option')),
    exchange text not null,
    tradingsymbol text not null,
    instrument_token bigint,
    expiry date,
    strike numeric(12, 2),
    option_type text,
    meta_json jsonb not null default '{}'::jsonb
);

create index if not exists phase0_universe_run_idx
    on ops.phase0_universe (run_id);

create index if not exists phase0_universe_token_idx
    on ops.phase0_universe (instrument_token);

create table if not exists market.underlying_snapshot_1m (
    ts timestamptz not null,
    source_type text not null,
    exchange text not null,
    tradingsymbol text not null,
    instrument_token bigint,
    last_price numeric(14, 4) not null,
    bid numeric(14, 4),
    ask numeric(14, 4),
    volume bigint,
    oi bigint,
    quote_quality text not null,
    raw_json jsonb not null,
    created_at timestamptz not null default now(),
    primary key (ts, tradingsymbol)
);

create index if not exists underlying_snapshot_token_ts_idx
    on market.underlying_snapshot_1m (instrument_token, ts desc);

create table if not exists market.option_snapshot_1m (
    ts timestamptz not null,
    exchange text not null,
    tradingsymbol text not null,
    instrument_token bigint not null,
    expiry date not null,
    strike numeric(12, 2) not null,
    option_type text not null,
    bid numeric(14, 4),
    ask numeric(14, 4),
    ltp numeric(14, 4),
    bid_qty integer,
    ask_qty integer,
    volume bigint,
    oi bigint,
    quote_quality text not null,
    last_trade_time timestamptz,
    raw_json jsonb not null,
    created_at timestamptz not null default now(),
    primary key (ts, tradingsymbol)
);

create index if not exists option_snapshot_expiry_strike_ts_idx
    on market.option_snapshot_1m (expiry, strike, option_type, ts desc);

create index if not exists option_snapshot_token_ts_idx
    on market.option_snapshot_1m (instrument_token, ts desc);

create table if not exists analytics.expiry_nodes_1m (
    ts timestamptz not null,
    expiry date not null,
    dte_days numeric(10, 4) not null,
    forward numeric(14, 4),
    atm_strike numeric(12, 2),
    atm_iv numeric(10, 6),
    iv_25c numeric(10, 6),
    iv_25p numeric(10, 6),
    rr25 numeric(10, 6),
    bf25 numeric(10, 6),
    source_count integer not null default 0,
    quality_score numeric(6, 3) not null default 0,
    method_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    primary key (ts, expiry)
);

create index if not exists expiry_nodes_expiry_ts_idx
    on analytics.expiry_nodes_1m (expiry, ts desc);
