# NIFTY Volatility Dashboard — Frontend Design Spec

## Context

The Python data pipeline (Phase 0) is complete: a worker ingests NIFTY option-chain data via Upstox, computes IV surfaces, constant-maturity metrics, percentiles, regime classification, and daily briefs — all written to Supabase. The frontend's job is to read these precomputed tables and present them as an interpretive analytics dashboard. The product's value is **interpretation**, not raw charts.

## Scope

**V1 ships 3 views**: Daily Brief, Surface Analytics, Flow Metrics.
**Deferred**: Alerts (Coming Soon placeholder), 3D Graph, Auth, Deployment.
**User**: Solo (you). No auth for V1. Architecture stays clean for multi-user later.

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Front-End Dominance formula | Spread: `IV7 - IV30` | Use existing worker output; ratio can be added later |
| Data refresh | Polling every 60s (during market hours) | Matches worker's 1-minute seal cadence, no extra infra |
| Strategy/Scenario section | Skipped for V1 | Focus on metrics and interpretation first |
| Design aesthetic | Modern dark with polish | Dark backgrounds, card layouts, good spacing, not Bloomberg-dense |
| V1 users | Solo | No auth, minimal RLS, focus on views and UX |
| Regime trail data | Derived from `metric_series_1m` | Query state_score/stress_score at day-close timestamps |
| Surface grid | 3x3 (P25/ATM/C25 x 7D/30D/90D) | Current DB schema, design grid-size-agnostic for expansion |
| Time scrubber | Current snapshot only for V1 | No historical heatmap replay; charts still show time-series |
| Chart time ranges | Configurable: 1D / 5D / 1M / 3M | Downsample for 1M (hourly) and 3M (daily) |
| Percentile UX | Color gradient on values | Blue (low) to red (extreme), universal, scannable |
| Navigation | Top tab bar | Maximizes horizontal space for charts |
| Interpretation prominence | Hero placement | Interpretation first, metrics second on Daily Brief |
| Alerts | Coming Soon placeholder | Skip for V1 |
| Flow layout | Scrollable stacked sections | All 6 sections visible, dual charts per section |
| Off-hours display | Last state + "Market Closed" badge | All views functional with stale data |

## Stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js App Router + TypeScript |
| Styling | Tailwind CSS (dark theme) |
| Charts | Apache ECharts (direct, no wrapper) |
| Data access | `@supabase/supabase-js` (browser, anon key) |
| Date handling | `date-fns` with IST timezone |
| State management | React state only (no Redux/Zustand) |

## Project Structure

```
web/
├── src/
│   ├── app/
│   │   ├── layout.tsx            # Root layout: dark theme, fonts, tab bar
│   │   ├── page.tsx              # Redirect to /brief
│   │   ├── brief/page.tsx        # Daily Brief view
│   │   ├── surface/page.tsx      # Surface Analytics view
│   │   ├── flow/page.tsx         # Flow Metrics view
│   │   └── alerts/page.tsx       # Coming Soon placeholder
│   ├── components/
│   │   ├── layout/
│   │   │   ├── TabBar.tsx        # Top navigation tabs
│   │   │   ├── MarketStatusBadge.tsx  # Live/Closed indicator
│   │   │   └── LoadingSkeleton.tsx
│   │   ├── brief/
│   │   │   ├── RegimeMap.tsx     # 2D quadrant scatter plot
│   │   │   ├── RegimeInterpretation.tsx  # Regime name + insight bullets
│   │   │   ├── KeyMetricCards.tsx  # Horizontal card row
│   │   │   └── DataQualityBar.tsx
│   │   ├── surface/
│   │   │   ├── IVHeatmap.tsx     # 3x3 delta-vs-tenor heatmap
│   │   │   ├── VolatilityLevel.tsx  # ATM IV cards + term spreads
│   │   │   ├── SkewStructure.tsx    # RR25 cards + spreads
│   │   │   ├── TailRiskPricing.tsx  # BF25 cards + spreads
│   │   │   └── FrontEndDominance.tsx
│   │   ├── flow/
│   │   │   ├── VolMomentum.tsx   # ATM IV change + spread charts
│   │   │   ├── SkewVelocity.tsx  # RR25 change + spread charts
│   │   │   ├── TailRiskMomentum.tsx  # BF25 change + spread charts
│   │   │   ├── TermStructureFlow.tsx  # Term spread change chart
│   │   │   ├── FEDFlow.tsx       # FED change chart
│   │   │   └── FlowChangeHeatmap.tsx  # 3x3 change percentile heatmap
│   │   └── shared/
│   │       ├── PercentileValue.tsx  # Number with percentile color
│   │       ├── MetricCard.tsx    # Label + value + percentile badge
│   │       ├── TimeRangeSelector.tsx  # 1D/5D/1M/3M toggle
│   │       ├── WindowSelector.tsx    # 5m/15m/60m/1D toggle
│   │       ├── SectionHeader.tsx
│   │       └── ChartContainer.tsx    # ECharts init/resize/dispose wrapper
│   ├── lib/
│   │   ├── supabase.ts          # Supabase client init (anon key)
│   │   ├── queries.ts           # All typed Supabase queries
│   │   └── constants.ts         # Metric keys, color scales, tenor codes
│   ├── hooks/
│   │   ├── usePolling.ts        # 60s interval hook (market-hours aware)
│   │   └── useMetricSeries.ts   # Query + cache for metric time-series
│   └── types/
│       └── index.ts             # TypeScript types matching Supabase schema
├── public/                      # Static assets
├── tailwind.config.ts
├── next.config.ts
├── package.json
└── tsconfig.json
```

## Supabase Tables Used (Browser-Facing)

| Table | Used By | Query Pattern |
|-------|---------|--------------|
| `dashboard_current` | Daily Brief | Single row: `select('*').single()` |
| `surface_cells_current` | Surface, Flow | All rows: `select('*')` |
| `metric_series_1m` | Surface, Flow, Brief | Filtered by metric_key, time range |
| `daily_brief_history` | Daily Brief | Last N rows by `brief_date` desc |

## View Designs

### 1. Daily Brief (Hero View)

**Layout**: Interpretation-first, metrics second.

**Top row (hero)**: Two-column layout
- **Left**: Regime Map (ECharts scatter plot)
  - 2D plot: X = state_score (0-100), Y = stress_score (-100 to 100)
  - 4 colored quadrant backgrounds split at `state = 50` and `stress = 0`: Calm (green), Transition (amber), Compression (blue), Stress (red)
  - Markers: filled circle for today, hollow circles for yesterday and 2-days-back
  - Trail derived from `metric_series_1m` querying `state_score` and `stress_score` at last minute of each trading day
- **Right**: Regime Interpretation panel
  - Regime name (large, quadrant-colored)
  - `insight_bullets_json` rendered as bullet list
  - `scenario_implications_json` if present

**Middle row**: Key Metric Cards (horizontal scroll if needed)
- Rendered from `key_cards_json` array in `dashboard_current`
- Each card: metric name, value (percentile-colored), percentile, interpretation label

**Bottom**: Data Quality bar
- From `data_quality_json`: usable options, selected strikes, last updated timestamp
- Subtle, non-intrusive

### 2. Surface Analytics

**Layout**: Scrollable single column.

**Section 1 — IV Heatmap**
- 3x3 ECharts heatmap (P25/ATM/C25 x 7D/30D/90D)
- Toggle: raw IV values / IV percentile
- Cell color: cool-to-hot based on value
- Data: `surface_cells_current`

**Section 2 — Volatility Level**
- 3 MetricCards: ATM IV 7D, 30D, 90D (from `metric_series_1m`, latest `atm_iv_*`)
- Below: Term spreads (7D-30D, 30D-90D, 7D-90D) with percentiles

**Section 3 — Skew Structure**
- 3 MetricCards: RR25 7D, 30D, 90D (from `metric_series_1m`, latest `rr25_*`)
- Below: Inter-tenor RR spreads with percentiles

**Section 4 — Tail Risk Pricing**
- 3 MetricCards: BF25 7D, 30D, 90D (from `metric_series_1m`, latest `bf25_*`)
- Below: Inter-tenor BF spreads with percentiles

**Section 5 — Front-End Dominance**
- Single prominent card: FED = IV7-IV30 (spread), percentile
- From `metric_series_1m`, latest `front_end_dominance`

**All numbers** color-coded by percentile. Missing data shows `-.--` in muted gray.

### 3. Flow Metrics

**Layout**: Scrollable stacked sections with global controls.

**Global controls** (sticky at top):
- Window selector: [5m | 15m | 60m | 1D] — filters which `d_*` metric keys are queried
- Time range selector: [1D | 5D | 1M | 3M] — controls chart x-axis range

**Sections 1-3** (Vol Momentum, Skew Velocity, Tail Risk Momentum):
- **Dual chart layout**: Left chart = metric change across tenors (7D/30D/90D overlaid), Right chart = inter-tenor spread changes
- Below each chart: current snapshot values as compact PercentileValue badges
- Data: `metric_series_1m` filtered by `d_atm_iv_*`, `d_rr25_*`, `d_bf25_*` + window_code

**Section 4 — Term Structure Flow**:
- Single chart: term spread changes (7D-30D, 30D-90D, 7D-90D) overlaid
- Data: `metric_series_1m` filtered by `d_term_*` keys (to be derived client-side from term spread metrics)

**Section 5 — FED Flow**:
- Single chart: front-end dominance change over time
- Data: `metric_series_1m` filtered by `d_front_end_dominance_*` + window_code

**Section 6 — Flow Change Heatmap**:
- 3x3 grid showing IV change for each delta-bucket/tenor combination in the selected window
- Data: For each cell (delta_bucket, tenor_code), query `metric_series_1m` for the corresponding `d_atm_iv_*` / `d_rr25_*` flow metric at the selected window. Map delta buckets to the closest available flow metric (ATM→atm_iv, P25/C25→derived from rr25/bf25 flows). This is an approximation — exact per-cell flow would need backend support
- Color scale: same percentile gradient as Surface heatmap

**Downsampling** for chart ranges:
- 1D: every minute (~375 points)
- 5D: every minute (~1,875 points)
- 1M: last minute per hour (~150 points, SQL `date_trunc('hour', ts)`)
- 3M: daily close (~60 points, SQL `date_trunc('day', ts)`)

### 4. Alerts (Placeholder)

- Tab exists in navigation
- Shows a "Coming Soon" card with brief description of planned alerts functionality

## Shared Components

### PercentileValue
Renders a numeric value with color derived from its percentile:
- 0-10: `#3B82F6` (blue) — Extremely low
- 10-20: `#60A5FA` (light blue) — Very low
- 20-40: `#6B7280` (gray) — Below average
- 40-60: `#9CA3AF` (light gray) — Normal
- 60-80: `#F59E0B` (amber) — Above average
- 80-90: `#EF4444` (light red) — Very high
- 90-100: `#DC2626` (red) — Extremely elevated

### MetricCard
Compact card with: label, value (PercentileValue), percentile badge, optional interpretation text.

### ChartContainer
Wrapper that: creates ECharts instance with dark theme on mount, handles window resize, disposes on unmount. Accepts `option` prop and calls `setOption` on change.

### MarketStatusBadge
- During market hours (9:15-15:30 IST, Mon-Fri, excluding NSE holidays): green dot + "Live" + last update time
- Outside: red dot + "Market Closed" + last seal timestamp

## Data Layer Architecture

```
Views (React components)
    ↓ call
Hooks (usePolling, useMetricSeries)
    ↓ call
Queries (lib/queries.ts — typed functions)
    ↓ call
Supabase Client (lib/supabase.ts — @supabase/supabase-js)
    ↓ REST
Supabase PostgREST (public schema, anon key, RLS)
```

The data layer is a clean abstraction: views never call Supabase directly. `queries.ts` contains all query logic. Swapping from polling to Realtime or adding an API layer later only changes the hooks/queries layer — zero component changes.

## Backend Prerequisites (User-Owned)

1. **Regime trail data**: Populate `state_score` and `stress_score` in `metric_series_1m` at day-close timestamps so the regime map can show a multi-day trail
2. **Anon RLS policies**: Ensure `public` schema tables have `SELECT` grant for the `anon` role so the browser can read with the Supabase anon key
3. **Flow metrics population**: Ensure `d_*` flow change metrics are being written to `metric_series_1m` with correct `window_code` values

## Design Principles

1. **Interpretation first**: The product explains what vol is doing, not just what the numbers are
2. **Percentile is king**: Every metric is contextualized by its historical percentile via color
3. **Modular architecture**: Each view, component, and query function is independent and replaceable
4. **Graceful degradation**: Missing data (90D tenor, provisional percentiles) shows `-.--` or a "provisional" label, never breaks the UI
5. **Market-aware**: Dashboard behavior changes cleanly between market hours and off-hours
6. **Dark polish**: Modern dark theme with clean cards, good typography, not cluttered terminal aesthetic
