# NIFTY Volatility Intelligence Web App

## Summary
- Build a desktop-first, analytics-only web app for `NIFTY` options that updates every minute and turns raw option-chain data into `Daily Brief`, `Surface`, `Flow`, `Graph`, and `Alerts` views.
- V1 is for your own use first, but the architecture should be public-product-ready later: tenant-aware data models, real auth, auditability, and provider abstraction from day one.
- The product’s value is interpretation, not just charts: it should tell the user whether vol is rich or cheap, whether skew is getting more defensive, whether pressure is front-end or back-end, and whether the move is accelerating or stabilizing.
- Official constraints that shape the design: Kite gives quotes, historical candles, instruments, and WebSockets, but the product must compute its own IV/Greeks/surface metrics; expired options history is not available from Kite, so percentiles must cold-start and mature over time. Sources: [market quotes](https://kite.trade/docs/connect/v3/market-quotes/), [historical](https://kite.trade/docs/connect/v3/historical/), [websocket](https://kite.trade/docs/connect/v3/websocket/), [rate limits](https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit), [Timescale hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/), [continuous aggregates](https://docs.timescale.com/use-timescale/latest/continuous-aggregates/about-continuous-aggregates/).

## Product Interpretation
- `Daily Brief` is the core surface: a plain-English regime translator with key metrics, percentile context, and descriptive implications. It replaces information overload with a single market read.
- `Surface` is the structural page: delta-vs-maturity heatmap plus ATM IV, term spreads, `25Δ RR`, `BF`, and front-end richness. It answers “where is the surface rich or cheap right now?”
- `Flow` is the motion page: percentile-of-change views for IV, skew, BF, and term spreads across `5m`, `15m`, `60m`, and `1D`. It answers “what is changing fastest?”
- `Graph` is exploratory, not primary. Ship it after `Daily Brief`, `Surface`, and `Flow`.
- `Alerts` are a first-class feature because the real product benefit is being notified when regime changes, not watching the screen all day.

## Metric Model
- `ATM IV` = current implied-vol level at a target maturity. Value: baseline uncertainty pricing.
- `Term spreads` such as `1W-1M`, `1M-3M`, `1W-3M`. Value: front-end event pressure versus broader regime repricing.
- `25Δ Risk Reversal` = downside versus upside skew. Value: crash/fear premium and directional asymmetry.
- `Butterfly / tail-risk pricing` = wing richness versus center. Value: convexity demand.
- `Momentum` = percentile of change in IV, RR, and BF over the chosen window. Value: elevated-versus-accelerating distinction.
- `Percentile` = current reading versus its own rolling history. Value: normalized interpretation across time.
- `Front-end dominance` in v1 should be explicitly defined as `1W ATM IV - 1M ATM IV` plus percentile. Keep it simple and interpretable.
- `Surface state` should be a composite of current level metrics; `Surface stress` should be a composite of change metrics.
- Regime map defaults: `Calm = low state/low stress`, `Transition = low state/high stress`, `Compression = high state/low stress`, `Stress = high state/high stress`.

## Recommended Stack
- Frontend: `Next.js + TypeScript + Tailwind CSS + Apache ECharts`. Use server-rendered summary pages and client-rendered charts.
- Auth: `Auth.js` with email magic link and roles like `admin` and `viewer`.
- Analytics backend: `FastAPI + Pydantic + NumPy + Polars + SciPy`. Python is the correct place for IV solving, interpolation, and percentile engines.
- Storage: `PostgreSQL + TimescaleDB` for minute snapshots and aggregates, `Redis` for live cache, cooldowns, and pub/sub.
- Notifications: in-app alerts plus email.
- Deployment: start on one Linux VM in an India region with Docker Compose for `web`, `api`, `db`, and `redis`; split services only after product fit.
- Data-provider policy: `Zerodha-first, pluggable later`. The provider interface must allow a future history vendor without rewriting the product.

## System Design
- Sync the gzipped `/instruments` dump daily and rebuild the active `NIFTY` universe before market open.
- Track `NIFTY` reference, near futures, and active option contracts out to roughly `90D`, limited by a dynamic strike band wide enough for ATM, `25Δ RR`, and `BF` calculations.
- Use WebSocket streaming for live quotes and minute snapshot sealing. Respect Zerodha limits such as `3` WebSocket connections with up to `3000` instruments each, plus REST limits like `1 r/s` for quote endpoints and `3 r/s` for historical data.
- Compute forward levels from futures and near-ATM parity checks, solve IV and Greeks in-house, and derive constant-maturity nodes in total-variance space.
- Use actual expiries for the `Surface` page, but use constant-maturity derived metrics for the regime map and `Daily Brief`.
- Launch with robust interpolation only: linear-in-variance across maturity and spline/monotone smoothing across delta for rendering. Do not make SABR a launch dependency.
- Because Kite cannot backfill expired options history, all percentile-backed metrics launch with a `provisional` maturity label and become more reliable as the internal store grows.

## Public APIs / Interfaces / Types
- `MarketDataProvider`: `sync_instruments()`, `stream_quotes(tokens)`, `fetch_historical(token, interval, from, to, include_oi)`, `get_ltp(tokens)`.
- `SurfaceSnapshot`: timestamp, underlying, expiry buckets, delta buckets, IV grid, percentile grid, ATM nodes, RR/BF nodes, front-end dominance, quality flags.
- `FlowSnapshot`: timestamp, window, IV/RR/BF change metrics, term-spread changes, regime classification.
- `DailyBrief`: timestamp, regime quadrant, headline bullets, descriptive interpretation, key cards, data-quality status.
- `AlertRule`: metric, scope, comparator, threshold, raw-or-percentile mode, cooldown, channel list, enabled flag.
- `GET /api/brief/current`
- `GET /api/surface/latest?view=iv|percentile`
- `GET /api/flow/latest?window=5m|15m|60m|1d`
- `GET /api/series?metric=...&range=...`
- `POST /api/alerts`
- `GET /api/stream/brief`

## Delivery Phases
- Phase 1: data plane. Instrument sync, live quote capture, minute snapshot persistence, quality flags, cold-start labels.
- Phase 2: quant engine. IV solver, delta mapping, ATM/RR/BF calculations, constant-maturity interpolation, percentile engine, regime map.
- Phase 3: product UI. `Daily Brief`, `Surface`, `Flow`, alert management, in-app notifications, email alerts.
- Phase 4: advanced and public-ready. 3D graph view, tenant hardening, audit logs, provider plug-in for richer history.

## Test Cases And Acceptance Criteria
- Instrument sync correctly rolls weekly and monthly expiries and removes stale contracts.
- Minute collector survives reconnects, missing ticks, and late quotes without corrupting snapshots.
- IV solver rejects crossed or illiquid markets safely and emits quality flags instead of bad numbers.
- `1W`, `1M`, and `3M` ATM IV plus `25Δ RR` and `BF` are reproducible from saved data.
- Regime map output is deterministic for the same input and changes only when source metrics change.
- Flow metrics update within one minute of the sealed snapshot.
- Alerts respect cooldowns and do not repeat on unchanged states.
- UI clearly labels `provisional percentile` metrics during the cold-start period.
- `Daily Brief` stays descriptive in v1 and does not emit explicit trade instructions.

## Assumptions And Defaults
- V1 covers `NIFTY` only.
- Cadence is one-minute intraday analytics during market hours.
- Guidance is descriptive, not advisory; the sketch’s `Strategies` box should be reframed as `Scenario implications`.
- Platform order is desktop web first, responsive mobile web next, native app much later.
- History target is a two-year percentile framework, but it begins by collecting now; add a second vendor only if needed.
- Zerodha is the first provider, but before any public launch you must verify redistribution and entitlement rules for live and derived market data.
