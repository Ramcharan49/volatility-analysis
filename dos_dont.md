# Final V1 Local-First Product, Data, and Quant Plan

## Summary

- `V1` runs locally for you as: `Next.js app on localhost` + `Python worker on localhost` + `cloud Supabase dev project`.
- `Supabase` is the only database in `v1`.
- `TimescaleDB` is not used in `v1`.
- `FastAPI` is not used in `v1`.
- `Zerodha API spike` is Phase 0 and is mandatory before building the dashboard.
- The product ships `Daily Brief`, `Surface`, `Flow`, and `Alerts`; `3D Graph` is deferred.
- The product stores only the raw data it actually needs for recomputation and debugging, then keeps the long-lived history in derived metric tables.

## Final V1 Stack

| Layer                | Final choice                                                                          |
| -------------------- | ------------------------------------------------------------------------------------- |
| Web app              | `Next.js App Router + TypeScript + Tailwind + Apache ECharts`                         |
| Auth                 | `Supabase Auth`                                                                       |
| DB                   | `Supabase Postgres`                                                                   |
| Python runtime       | `Python 3.12` local worker                                                            |
| Python libs          | `kiteconnect`, `numpy`, `scipy`, `polars`, `psycopg`, `pydantic-settings`, `tenacity` |
| Frontend data access | `supabase-js` with RLS                                                                |
| Email later          | `Resend` via custom SMTP                                                              |
| Local dev mode       | `web local + worker local + hosted Supabase dev project`                              |

## Exact Local Setup

- Run the web app at `http://localhost:3000`.
- Run the Python worker locally from the same machine.
- Point both to a `Supabase dev project` in `South Asia (Mumbai) / ap-south-1`.
- Keep Zerodha secrets only on the local worker, never in the browser.
- The browser reads only precomputed tables from Supabase.
- The worker is the only process that talks to Zerodha and writes market/analytics data.

## Exact Supabase Project Settings

- Project region: `South Asia (Mumbai) / ap-south-1`
- `Enable Data API`: `ON`
- `Enable automatic RLS`: `ON`
- Keep default `Postgres 17`
- Exposed schema for `v1`: `public`
- Private schemas for `v1`: `market`, `analytics`, `ops`
- Extensions to enable now: `pgcrypto`, `pg_cron`
- Extensions to not enable now: `timescaledb`, `pg_partman`
- Auth config for local dev:
- `Site URL = http://localhost:3000`
- add redirect URLs for `http://localhost:3000/**` and `http://127.0.0.1:3000/**`
- Auth email:
- default SMTP is fine only for your own team emails during setup
- before inviting real users, configure custom SMTP
- DB connection for the worker:
- use `Supavisor session mode` on port `5432`
- use a dedicated DB role like `worker_rw`, not the service role key

## Why V1 Does Not Need TimescaleDB

- `NIFTY only`
- `1-minute cadence only`
- short raw-retention window
- long-lived history stored as compact derived metrics, not raw ticks
- frontend reads only precomputed current/history tables, not giant raw time-series tables
- Supabase’s current docs still mark `timescaledb` as deprecated on `Postgres 17`
- `pg_partman` is a later scaling tool for native partitions, not something we need to ship the first useful release

## Zerodha Phase 0 Spike

1. Validate login flow and token exchange.
2. Download and persist the instruments dump.
3. Subscribe to `NIFTY`, front future, next future, and a controlled sample of NIFTY options.
4. Stream for at least `30 minutes`.
5. Persist minute snapshots into the dev DB.
6. Compute one `ATM IV`, one `25Δ RR`, and one `25Δ BF` end-to-end.
7. Confirm the dashboard can read those rows from Supabase.
8. Record all field mappings and quality filters before UI work starts.

## Exact Table Set

| Table                    | Schema      | Purpose                                                                           | Retention                  | Exposed to browser |
| ------------------------ | ----------- | --------------------------------------------------------------------------------- | -------------------------- | ------------------ |
| `instrument_catalog`     | `market`    | Zerodha instruments dump, active contracts, lot size, expiry, strike, option type | current + audit timestamps | No                 |
| `underlying_snapshot_1m` | `market`    | `NIFTY` index and near futures minute snapshots                                   | 30 days                    | No                 |
| `option_snapshot_1m`     | `market`    | Compact minute snapshots for tracked option contracts                             | 14 days                    | No                 |
| `expiry_nodes_1m`        | `analytics` | Per-expiry forward, ATM IV, 25C IV, 25P IV, RR25, BF25, quality flags             | 180 days                   | No                 |
| `metric_baselines_daily` | `analytics` | Rolling percentile baselines for level metrics                                    | 2 years                    | No                 |
| `flow_baselines`         | `analytics` | Rolling percentile baselines for intraday change windows                          | 2 years                    | No                 |
| `metric_series_1m`       | `public`    | Long-lived derived history for charting and current cards                         | 2 years                    | Yes                |
| `surface_cells_current`  | `public`    | Latest heatmap cells for `Surface` page                                           | current only               | Yes                |
| `dashboard_current`      | `public`    | Latest regime quadrant, key cards, insight bullets, scenario implications         | current only               | Yes                |
| `daily_brief_history`    | `public`    | One saved brief per trading day close, plus manual checkpoints if desired         | 2 years                    | Yes                |
| `profiles`               | `public`    | User profile and settings                                                         | life of account            | Yes, RLS           |
| `alert_rules`            | `public`    | User-configured alert rules                                                       | life of account            | Yes, RLS           |
| `alert_events`           | `public`    | Fired alerts and email delivery status                                            | 1 year                     | Yes, RLS           |
| `worker_heartbeat`       | `ops`       | Last sync time, last snapshot time, status, error message                         | 30 days                    | No                 |

## Exact Core Columns

- `market.option_snapshot_1m`
- `ts`, `instrument_token`, `tradingsymbol`, `expiry`, `strike`, `option_type`, `bid`, `ask`, `ltp`, `last_trade_time`, `volume`, `oi`, `bid_qty`, `ask_qty`, `quote_quality`
- `analytics.expiry_nodes_1m`
- `ts`, `expiry`, `dte_days`, `forward`, `atm_strike`, `atm_iv`, `iv_25c`, `iv_25p`, `rr25`, `bf25`, `source_count`, `quality_score`
- `public.metric_series_1m`
- `ts`, `metric_key`, `tenor_code`, `window_code`, `value`, `percentile`, `provisional`, `source`
- `public.surface_cells_current`
- `as_of`, `tenor_code`, `delta_bucket`, `iv`, `iv_percentile`, `quality_score`
- `public.dashboard_current`
- `as_of`, `state_score`, `stress_score`, `quadrant`, `key_cards_json`, `insight_bullets_json`, `scenario_implications_json`

## Exact Storage Policy

- Store `one-minute snapshots`, not raw ticks.
- Track all `NIFTY` option contracts with expiry up to `90 calendar days` if token count stays below WebSocket limits.
- If token count gets too large, limit the universe to strikes inside a dynamic `0.80x to 1.20x` moneyness band around the inferred forward.
- Keep raw minute option snapshots only `14 days`.
- Keep derived metrics `2 years`.
- Keep the full current surface only as the latest snapshot, not a huge historical surface cube in `v1`.

## Exact Calculation Pipeline

| Output                  | Exact calculation                                                                                                                                | Basis                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| Quote price             | `mid = (best_bid + best_ask)/2` if both valid and spread sane; else fallback to recent `ltp`; else discard                                       | chosen v1 quote-cleaning rule                                             |
| Time to expiry          | `T = max((expiry_ts - snapshot_ts) / 365d, epsilon)`                                                                                             | standard                                                                  |
| Forward                 | preferred: put-call parity near ATM, `F = K + exp(rT) * (C_mid - P_mid)`; fallback: aligned future price; fallback: `spot * exp(rT)`             | standard + chosen fallback chain                                          |
| IV                      | solve for `σ` from option mid price using forward-form European pricing (`Black 76` style)                                                       | canonical                                                                 |
| Delta                   | use forward delta from the same solved vol and forward                                                                                           | chosen v1 convention                                                      |
| ATM IV                  | choose strike nearest forward and use the average of valid call/put IVs there; if both unavailable, interpolate from nearest surrounding strikes | chosen robust v1 rule                                                     |
| `RR25`                  | `σ_25C - σ_25P`                                                                                                                                  | canonical market convention, consistent with CME risk-reversal definition |
| `BF25`                  | `0.5 * (σ_25C + σ_25P) - σ_ATM`                                                                                                                  | chosen standard smile/convexity convention                                |
| Constant maturity ATM   | interpolate total variance `w = σ²T` between surrounding expiries to target tenors `7D`, `30D`, `90D`, then convert back to vol                  | chosen v1 interpolation rule                                              |
| Constant maturity RR/BF | interpolate `σ_25C`, `σ_25P`, and `σ_ATM` in total variance by tenor, then recompute `RR25` and `BF25` at target tenor                           | chosen v1 interpolation rule                                              |
| Term spread             | `ATM_IV_7D - ATM_IV_30D`, `ATM_IV_30D - ATM_IV_90D`, `ATM_IV_7D - ATM_IV_90D`                                                                    | product metric                                                            |
| Front-end dominance     | same as `ATM_IV_7D - ATM_IV_30D` in `v1`                                                                                                         | product metric                                                            |
| Flow change             | `metric_now - metric_(now-window)` for windows `5m`, `15m`, `60m`, `1D`                                                                          | product metric                                                            |
| Level percentile        | empirical percentile of current level vs trailing daily-close history of the same metric                                                         | chosen v1 percentile method                                               |
| Flow percentile         | empirical percentile of current window-change vs trailing historical changes of the same window and metric                                       | chosen v1 percentile method                                               |
| State score             | mean of percentiles for `ATM_IV_7D`, `ATM_IV_30D`, `front_end_dominance`, `-RR25_30D`, `BF25_30D`                                                | product-specific composite                                                |
| Stress score            | mean of percentiles for absolute `1D` changes in `ATM_IV_7D`, `RR25_30D`, `BF25_30D`, `front_end_dominance`                                       | product-specific composite                                                |
| Regime quadrant         | `Calm` if both scores < 50, `Transition` if state < 50 and stress >= 50, `Compression` if state >= 50 and stress < 50, `Stress` if both >= 50    | product-specific rule                                                     |
| Daily brief text        | deterministic rules from quadrant, key level metrics, and strongest flow changes; no LLM in `v1`                                                 | product-specific rule                                                     |

## Exact Surface Grid for V1

- Use a fixed delta grid of `P10`, `P25`, `ATM`, `C25`, `C10`.
- Use fixed tenor targets `7D`, `30D`, `90D`.
- `surface_cells_current` is therefore a `5 x 3` grid at every refresh.
- This is deliberate: it matches the sketch’s intent, keeps the UI interpretable, and avoids overbuilding a full dense surface before the product proves itself.

## Exact Metric Keys in `metric_series_1m`

- `atm_iv_7d`
- `atm_iv_30d`
- `atm_iv_90d`
- `rr25_7d`
- `rr25_30d`
- `rr25_90d`
- `bf25_7d`
- `bf25_30d`
- `bf25_90d`
- `term_7d_30d`
- `term_30d_90d`
- `term_7d_90d`
- `front_end_dominance`
- `state_score`
- `stress_score`
- `d_atm_iv_7d_5m`, `d_atm_iv_7d_15m`, `d_atm_iv_7d_60m`, `d_atm_iv_7d_1d`
- `d_rr25_30d_5m`, `d_rr25_30d_15m`, `d_rr25_30d_60m`, `d_rr25_30d_1d`
- `d_bf25_30d_5m`, `d_bf25_30d_15m`, `d_bf25_30d_60m`, `d_bf25_30d_1d`
- `d_front_end_dominance_5m`, `d_front_end_dominance_15m`, `d_front_end_dominance_60m`, `d_front_end_dominance_1d`

## Exact Browser-Facing Product Reads

- `Daily Brief` reads `public.dashboard_current` and `public.daily_brief_history`
- `Surface` reads `public.surface_cells_current` and selected `public.metric_series_1m` rows
- `Flow` reads selected `public.metric_series_1m` rows filtered by `window_code`
- `Alerts` reads `public.alert_rules` and `public.alert_events`
- The browser does not query `market.*` or `analytics.*`

`Flow` remains multi-window for exploratory motion. `Stress` is explicitly macro and uses `1D` change percentiles only.

## Exact Alert Rule Model

- `metric_key`
- `tenor_code`
- `window_code`
- `threshold_type` as `raw` or `percentile`
- `comparator` as `>`, `<`, `crosses_above`, `crosses_below`
- `threshold_value`
- `cooldown_minutes`
- `channel` as `in_app` or `email`
- `enabled`

## Test Cases and Scenarios

- Zerodha spike proves one minute of live data can be stored and transformed correctly.
- Put-call parity derived forward is stable across liquid near-ATM strikes.
- IV solver rejects bad quotes and records `quote_quality` correctly.
- `RR25` and `BF25` are reproducible from saved minute snapshots.
- Daily brief text changes deterministically when metric thresholds change.
- Browser reads only exposed `public` tables with RLS.
- `market.*` and `analytics.*` remain inaccessible from the browser.
- Retention jobs clean raw `14-day` data without affecting long-history derived metrics.
- The full app works locally with web + worker on your machine against the hosted Supabase dev project.

## Assumptions and Defaults

- `NIFTY only`
- `1-minute cadence`
- `local worker`, not cloud worker, for now
- `cloud Supabase dev project`, not fully local Postgres, for now
- `robust and simple quant mode`
- `no TimescaleDB in v1`
- `no FastAPI in v1`
- `deterministic rules`, not LLMs, for interpretation in `v1`

## References

- Zerodha market data docs: https://kite.trade/docs/connect/v3/market-quotes/ , https://kite.trade/docs/connect/v3/websocket/ , https://kite.trade/docs/connect/v3/historical/
- Supabase setup and security: https://supabase.com/docs/guides/platform/regions , https://supabase.com/docs/guides/database/connecting-to-postgres , https://supabase.com/docs/guides/database/hardening-data-api , https://supabase.com/docs/guides/api/securing-your-api , https://supabase.com/docs/guides/database/postgres/row-level-security , https://supabase.com/docs/guides/database/extensions/timescaledb , https://supabase.com/docs/guides/database/partitions , https://supabase.com/docs/guides/auth/auth-smtp
- Option pricing foundations: Black & Scholes (1973) via https://econpapers.repec.org/RePEc:ucp:jpolec:v:81:y:1973:i:3:p:637-54 , Merton (1973) via https://robertcmerton.com/publication/theory-of-rational-option-pricing/ , Black (1976) via https://econpapers.repec.org/RePEc:eee:jfinec:v:3:y:1976:i:1-2:p:167-179
- Risk-reversal/skew convention: https://www.cmegroup.com/education/courses/introduction-to-cvol/introduction-to-cvol-skew.html
- NSE index-option convention examples: https://www.nseindia.com/products-services/equity-derivatives-bank-nifty-option-contract-specification-weekly , https://www.nseindia.com/products-services/equity-derivatives-bank-nifty-option-contract-specification-monthly
