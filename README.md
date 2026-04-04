# NIFTY Volatility Intelligence

Real-time volatility surface analytics for NIFTY 50 index options. Transforms raw option-chain data into structured metrics, regime classification, and a daily brief — updated every minute during market hours.

## Overview

This system ingests live NIFTY options data via Upstox and daily historical close data via either Upstox or public NSE UDiFF FO bhavcopies, computes implied volatility across the strike/expiry grid, interpolates to constant-maturity tenors (7D, 30D, 90D), and derives level metrics (ATM IV, risk reversal, butterfly), flow metrics (rate-of-change across multiple windows), percentile context, and a composite regime score.

The output is a structured analytics layer suitable for powering dashboards, alerts, and trading decision support.

### Key Metrics

| Metric | Description |
|--------|-------------|
| **ATM IV** | At-the-money implied volatility at 7D, 30D, 90D tenors |
| **25-Delta Risk Reversal** | Put-call skew: `IV(25d call) - IV(25d put)` |
| **25-Delta Butterfly** | Wing convexity: `0.5 * (IV(25d call) + IV(25d put)) - ATM IV` |
| **Term Spreads** | Front-end vs back-end pressure: `ATM(7D) - ATM(30D)`, etc. |
| **Flow Metrics** | Rate of change across 5m, 15m, 60m, and 1D windows |
| **State Score** | Composite level percentile (is vol high or low vs history?) |
| **Stress Score** | Composite flow percentile (is vol moving fast?) |
| **Regime Quadrant** | Calm / Transition / Compression / Stress classification |

## Architecture

```
Upstox API                           NSE UDiFF Daily Files
    |                                       |
    v                                       v
[Instruments Sync] --> [Universe Builder]   [Daily History Source]
                 \            |                    |
                  \           v                    |
                   --> [Quote Fetcher / WebSocket]|
                                 |                |
                                 v                v
                        [Normalized Option Rows / Underlyings]
                                         |
                                         v
                              [Option Price Cleaning]
                                         |
                                         v
                            [Put-Call Parity Forward]
                                         |
                                         v
                         [Black-76 IV Solver + Delta]
                                         |
                                         v
                               [Expiry Nodes]
                              (per-expiry vol surface)
                                         |
                                         v
                        [Constant-Maturity Interpolation]
                         (total-variance space, 7D/30D/90D)
                                         |
                                         v
                  [Level Metrics]   [Surface Grid]   [Flow Metrics]
                          |               |               |
                          v               v               v
                  [Percentile Engine] --> [Regime Scores] --> [Daily Brief]
                                                                  |
                                                                  v
                                                            [Supabase DB]
```

### Quantitative Methods

- **Forward Estimation**: Put-call parity across near-ATM strikes (median of top-3 candidates by proximity), with futures fallback
- **IV Solver**: Black-76 model with bisection root-finding (tolerance: 1e-6, max 120 iterations)
- **Delta Convention**: Black-76 forward delta (`N(d1)` for calls, `N(d1) - 1` for puts)
- **25-Delta Extraction**: Linear interpolation in delta space between bracketing strikes
- **CM Interpolation**: Linear interpolation in total-variance space (`w = IV^2 * T`) to avoid calendar arbitrage
- **Percentiles**: Empirical rank-based (`rank / (N+1) * 100`), provisional flag until 60 days of history

### Strike Filtering

Configurable strike step (`PHASE0_STRIKE_STEP`) filters out intermediate, illiquid strikes before IV/delta computation. For NIFTY, `100` is recommended (keeps only strikes at 100-point intervals: 22000, 22100, 22200...). All strikes are retained for put-call parity forward estimation.

### Quality Controls

- **Per-node quality score**: Weighted composite of forward quality (40%), ATM quality (35%), and RR/BF bracketing quality (25%)
- **CM quality gate**: Expiry nodes with quality score < 0.4 are excluded from constant-maturity bracket selection (graceful fallback at half-threshold)
- **Source priority**: `live > backfill > snapshot` — live data is never overwritten by lower-priority sources

## Project Structure

```
.
├── phase0/                      # Core analytics engine
│   ├── config.py                # Settings and environment configuration
│   ├── instruments.py           # Universe building and strike selection
│   ├── interpolation.py         # Constant-maturity interpolation
│   ├── live.py                  # WebSocket minute accumulator
│   ├── metrics.py               # Level metrics, flow metrics, surface grid
│   ├── models.py                # Data classes (ExpiryNode, ConstantMaturityNode)
│   ├── quant.py                 # Black-76 pricing, IV solver, delta interpolation
│   └── providers/upstox/        # Upstox API client, quotes, instruments
│
├── worker/                      # Production pipeline
│   ├── main.py                  # Worker lifecycle (pre-market → market → post-market)
│   ├── gap_fill.py              # Historical backfill for missed days
│   ├── calendar.py              # NSE trading calendar
│   ├── db.py                    # Supabase persistence (idempotent upserts)
│   ├── percentile.py            # Empirical percentiles, state/stress scores
│   ├── daily_brief.py           # Rule-based daily brief generation
│   └── buffers.py               # Flow ring buffer for intraday windows
│
├── tests/                       # 174 unit and integration tests
├── supabase/migrations/         # Database schema migrations
├── verify_pipeline.py           # Snapshot and history verification tool
├── phase0_probe.py              # Auth, probe, and live validation CLI
└── .env                         # Environment configuration
```

## Setup

### Prerequisites

- Python 3.9+
- Upstox developer account with API credentials
- Supabase project (free tier works)

### Installation

```bash
git clone <repo-url>
cd finance-app
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
pip install -r requirements-phase0.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in:

```env
PHASE0_PROVIDER=upstox
UPSTOX_API_KEY=your-api-key
UPSTOX_API_SECRET=your-api-secret
UPSTOX_REDIRECT_URL=http://127.0.0.1:8000/callback
SESSION_STATE_PATH=./state/session.json
SUPABASE_DB_URL_SESSION=postgresql://postgres:password@db.project-ref.supabase.co:5432/postgres
PHASE0_STRIKE_STEP=100
PHASE0_STRIKES_AROUND_ATM=15
PHASE0_DAILY_HISTORY_SOURCE=nse_udiff
```

`PHASE0_DAILY_HISTORY_SOURCE=nse_udiff` requires no additional API setup. It fetches public NSE FO UDiFF bhavcopy archives over HTTPS. Upstox credentials are still required for live mode and full 1-minute historical replay.

### Database Setup

Apply migrations via the Supabase dashboard or CLI:

```
supabase/migrations/20260315_phase0_initial_schema.sql
supabase/migrations/20260319_provider_abstraction.sql
supabase/migrations/20260321_phase1_tables.sql
supabase/migrations/20260404_history_backfill_audit.sql
```

## Usage

### Authentication

Authenticate with Upstox daily (tokens expire at end of day):

```bash
python phase0_probe.py auth --code <AUTH_CODE>
```

### Snapshot Mode

Capture a single point-in-time from REST quotes. Works anytime (including after hours for closing snapshot):

```bash
python verify_pipeline.py snapshot
python verify_pipeline.py snapshot --skip-db    # CSV only, no DB writes
```

### History Mode

Replay a full trading day (375 minutes) from historical 1-minute candles:

```bash
python verify_pipeline.py history --date 2026-03-30
python verify_pipeline.py history --date 2026-03-30 --skip-db
```

### Daily Close Mode

Reconstruct a single end-of-day close snapshot without replaying every minute:

```bash
python verify_pipeline.py daily --date 2026-04-02
python verify_pipeline.py daily --date 2026-04-02 --source nse_udiff --skip-db
python verify_pipeline.py daily --date 2026-04-02 --source upstox
```

Use `nse_udiff` for fast free daily history. Use `upstox` when you want the old broker-backed daily-close path.

### Range Backfill

```bash
python backfill.py --from 2026-03-24 --to 2026-04-02
python backfill.py --from 2026-03-24 --to 2026-04-02 --mode daily --daily-source nse_udiff
python backfill.py --from 2025-04-01 --to 2026-04-02 --daily-before 2026-03-01 --daily-source nse_udiff
```

Range jobs continue date-by-date when a daily file is missing, unsupported, or malformed. Successful dates still write artifacts, and DB-enabled runs also write a per-run audit trail when the audit migration is applied.

### Live Worker

Continuous pipeline during market hours. Handles pre-market gap-fill, live WebSocket accumulation, per-minute analytics, post-market baselines, and daily brief generation:

```bash
python -m worker.main
```

The worker runs autonomously until stopped with `Ctrl+C`.

### Running Tests

```bash
python -m pytest tests/ -v
```

## Database Schema

| Table | Schema | Description |
|-------|--------|-------------|
| `expiry_nodes_1m` | `analytics` | Per-expiry IV surface, 1-minute granularity |
| `constant_maturity_nodes_1m` | `analytics` | Interpolated 7D/30D/90D nodes |
| `metric_baselines_daily` | `analytics` | Daily closing values for percentile computation |
| `flow_baselines` | `analytics` | Daily closing flow values |
| `metric_series_1m` | `public` | Level + flow metrics with percentiles |
| `surface_cells_current` | `public` | Live 3x3 volatility surface grid |
| `dashboard_current` | `public` | Dashboard singleton (regime, scores, brief) |
| `daily_brief_history` | `public` | Historical daily briefs |
| `worker_heartbeat` | `ops` | Worker liveness tracking |
| `gap_fill_log` | `ops` | Backfill audit trail |
| `history_backfill_run` | `ops` | Manual range-backfill run audit |
| `history_backfill_day_log` | `ops` | Per-date status for manual range backfills |

All writes use idempotent upserts (`ON CONFLICT DO UPDATE`) with source-mode priority guards.

## Roadmap

- [ ] **Frontend dashboard** — Next.js web app with Daily Brief, Surface heatmap, Flow charts, and Graph views
- [ ] **Alerting system** — Configurable alerts on regime changes, percentile breaches, and skew shifts
- [ ] **SABR calibration** — Replace linear delta interpolation with SABR model for smoother smile fitting
- [ ] **Multi-underlying support** — Extend beyond NIFTY to Bank Nifty, FinNifty, and single-stock options
- [ ] **Historical percentile backfill** — Bootstrap percentile engine from expired options data for faster cold-start
- [ ] **Intraday surface snapshots** — Store full surface at configurable intervals for historical replay
- [ ] **API layer** — FastAPI service exposing metrics, surface, and brief endpoints for external consumers

## License

Private. All rights reserved.
