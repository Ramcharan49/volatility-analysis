# NIFTY Volatility Intelligence

Real-time volatility surface analytics for NIFTY 50 index options. Transforms raw option-chain data into structured metrics, regime classification, and a daily brief — updated every minute during market hours.

## Overview

This system ingests live and historical NIFTY options data via the Upstox API, computes implied volatility across the strike/expiry grid, interpolates to constant-maturity tenors (7D, 30D, 90D), and derives level metrics (ATM IV, risk reversal, butterfly), flow metrics (rate-of-change across multiple windows), percentile context, and a composite regime score.

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
Upstox API
    |
    v
[Instruments Sync] --> [Universe Builder] --> [Quote Fetcher / WebSocket]
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
UPSTOX_REDIRECT_URL=https://localhost:8000
SUPABASE_DB_URL_SESSION=postgresql://postgres:password@db.project-ref.supabase.co:5432/postgres
PHASE0_STRIKE_STEP=100
```

### Database Setup

Apply migrations via the Supabase dashboard or CLI:

```
supabase/migrations/20260315_phase0_initial_schema.sql
supabase/migrations/20260319_provider_abstraction.sql
supabase/migrations/20260321_phase1_tables.sql
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
