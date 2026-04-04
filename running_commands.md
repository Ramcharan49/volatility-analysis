# Running Commands

## Prerequisites

- Run all commands from the repo root: `C:\finance app`
- Make sure your virtual environment is active, or replace `python` with `.\venv\Scripts\python`
- Make sure `.env` is filled correctly before any DB-writing run
- Use `--skip-db` when you only want artifacts/CSV output and do not want to write to Supabase

## Upstox Auth

Use this before live mode or any Upstox-backed historical run:

```bash
python phase0_probe.py auth --code <UPSTOX_AUTH_CODE>
```

If you want the login URL printed instead of opening the browser:

```bash
python phase0_probe.py auth --no-browser
```

## Verify Pipeline Commands

### 1. Snapshot Mode

Single-point pipeline run from REST quotes.

```bash
python verify_pipeline.py snapshot
python verify_pipeline.py snapshot --skip-db
```

### 2. Full Intraday Historical Replay

Rebuild one full trading day from Upstox 1-minute candles.

```bash
python verify_pipeline.py history --date 2026-03-30
python verify_pipeline.py history --date 2026-03-30 --skip-db
```

### 3. Daily Close History

Fast close-only run for a single day.

Use NSE UDiFF:

```bash
python verify_pipeline.py daily --date 2026-04-02
python verify_pipeline.py daily --date 2026-04-02 --source nse_udiff --skip-db
```

Use Upstox instead:

```bash
python verify_pipeline.py daily --date 2026-04-02 --source upstox
python verify_pipeline.py daily --date 2026-04-02 --source upstox --skip-db
```

## Backfill Commands

### 1. Full Minute Range Backfill

Uses Upstox 1-minute history.

```bash
python backfill.py --from 2026-03-24 --to 2026-04-02
python backfill.py --from 2026-03-24 --to 2026-04-02 --skip-db
```

### 2. Daily Close Range Backfill

Uses daily close data only. This is the fast path for long history.

```bash
python backfill.py --from 2026-03-24 --to 2026-04-02 --mode daily --daily-source nse_udiff
python backfill.py --from 2026-03-24 --to 2026-04-02 --mode daily --daily-source nse_udiff --skip-db
```

Use Upstox instead:

```bash
python backfill.py --from 2026-03-24 --to 2026-04-02 --mode daily --daily-source upstox
```

### 3. Hybrid Backfill

Use daily mode before a cutoff, then full minute mode after it.

```bash
python backfill.py --from 2025-04-01 --to 2026-04-02 --daily-before 2026-03-01 --daily-source nse_udiff
python backfill.py --from 2025-04-01 --to 2026-04-02 --daily-before 2026-03-01 --daily-source nse_udiff --skip-db
```

### 4. One-Year Daily UDiFF Rebuild

This is the main historical rebuild command for the current setup.

```bash
python backfill.py --from 2025-04-02 --to 2026-04-02 --mode daily --daily-source nse_udiff
```

Dry run with artifacts only:

```bash
python backfill.py --from 2025-04-02 --to 2026-04-02 --mode daily --daily-source nse_udiff --skip-db
```

### 5. Layer 1-Minute History on Top Later

After the daily-close base is built, use full mode for selected intraday ranges:

```bash
python backfill.py --from 2026-01-01 --to 2026-01-31
python backfill.py --from 2026-03-24 --to 2026-04-02
```

## Phase 0 Probe Commands

### 1. Offline Probe

```bash
python phase0_probe.py probe
python phase0_probe.py probe --skip-db
python phase0_probe.py probe --allow-ltp-fallback
```

### 2. Live Validation

```bash
python phase0_probe.py live
python phase0_probe.py live --duration-minutes 30
python phase0_probe.py live --skip-db
```

### 3. Replay a Saved Live Manifest

```bash
python phase0_probe.py replay --manifest <PATH_TO_MANIFEST_JSON>
python phase0_probe.py replay --manifest <PATH_TO_MANIFEST_JSON> --skip-db
```

### 4. Expired-Instruments History Probe

```bash
python phase0_probe.py history-probe
```

## Live Worker

Main live ingestion / minute-seal worker:

```bash
python -m worker.main
```

## Supabase Reset Before a Fresh Yearly Rebuild

Run this in the Supabase SQL editor or through MCP if you want a clean derived-state reset before rebuilding history:

```sql
begin;

insert into public.dashboard_current (id, as_of)
values (1, now())
on conflict (id) do nothing;

truncate table
  analytics.expiry_nodes_1m,
  analytics.constant_maturity_nodes_1m,
  analytics.metric_baselines_daily,
  analytics.flow_baselines,
  public.metric_series_1m,
  public.surface_cells_current,
  public.daily_brief_history,
  ops.history_backfill_day_log,
  ops.history_backfill_run,
  ops.gap_fill_log;

update public.dashboard_current
set
  as_of = now(),
  state_score = null,
  stress_score = null,
  quadrant = null,
  key_cards_json = '[]'::jsonb,
  insight_bullets_json = '[]'::jsonb,
  scenario_implications_json = '[]'::jsonb,
  data_quality_json = '{}'::jsonb,
  updated_at = now()
where id = 1;

commit;
```

## Useful Notes

- `verify_pipeline.py history` and `backfill.py --mode full` use Upstox minute history
- `verify_pipeline.py daily` and `backfill.py --mode daily` can use `nse_udiff` or `upstox`
- `nse_udiff` is the recommended source for long daily-close history because it is free and much faster
- Daily mode gives you level history plus `1d` flow history; it does not create true `5m`, `15m`, or `60m` flow history
- Range backfills now treat missing daily UDiFF dates as `no_data` and continue
