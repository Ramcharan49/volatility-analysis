# Surface Page Architecture

> **IMPORTANT**: If you change any metric keys, data sources, or component structure described here, UPDATE THIS DOCUMENT to reflect the changes.

## Overview

The Surface page displays volatility surface metrics as interactive time-series charts with selectable tenors and display toggles. It replaces the previous static-card layout.

## Page Structure

```
┌─ Global Controls Bar (sticky) ──────────────────────┐
│  Range: [1W | 1M | 3M]   "Each point = 1 trading day" │
└──────────────────────────────────────────────────────┘

┌─ IV Heatmap (3x3 grid) ─────────────────────────────┐
│  Existing component, unchanged                        │
└──────────────────────────────────────────────────────┘

┌─ Volatility Level ──────────────────────────────────┐
│  [ATM IV chart: 7D|30D|90D]  [IV Term Spread chart]  │
└──────────────────────────────────────────────────────┘

┌─ Skew Structure ────────────────────────────────────┐
│  [RR25 chart: 7D|30D|90D]  [RR Term Spread chart]    │
└──────────────────────────────────────────────────────┘

┌─ Tail Risk Pricing ────────────────────────────────┐
│  [BF25 chart: 7D|30D|90D]  [BF Term Spread chart]    │
└──────────────────────────────────────────────────────┘

┌─ Front-End Dominance ───────────────────────────────┐
│  [FED chart: full width]                               │
└──────────────────────────────────────────────────────┘
```

## Data Flow

1. **Surface page** (`web/src/app/surface/page.tsx`) fetches ALL 13 metrics in one batch:
   - `getMetricSeries(ALL_METRIC_KEYS, range)` → time-series data
   - `getLatestMetrics(ALL_METRIC_KEYS)` → latest snapshot values
   - `getSurfaceCells()` → heatmap cell data
2. Results are grouped into `seriesMap: Map<metric_key, MetricRow[]>` and `latestMap: Map<metric_key, MetricRow>`
3. Each `SurfaceMetricChart` receives the full maps and reads only its own keys
4. Global range change triggers one refetch, all charts update

## Metric Keys Used

### Direct metrics (stored in `metric_series_1m` table)

| Section | Left Chart | Keys |
|---------|-----------|------|
| Volatility Level | ATM IV | `atm_iv_7d`, `atm_iv_30d`, `atm_iv_90d` |
| Skew Structure | 25Δ Risk Reversal | `rr25_7d`, `rr25_30d`, `rr25_90d` |
| Tail Risk Pricing | 25Δ Butterfly | `bf25_7d`, `bf25_30d`, `bf25_90d` |
| Front-End Dominance | FED Spread | `front_end_dominance` |

### Pre-computed spreads (stored in `metric_series_1m` table)

| Section | Right Chart | Keys |
|---------|------------|------|
| Volatility Level | IV Term Spread | `term_7d_30d`, `term_30d_90d`, `term_7d_90d` |

### Client-computed spreads (NOT in DB — computed by subtracting two series aligned by date)

| Section | Right Chart | Computation |
|---------|------------|-------------|
| Skew Structure | RR Term Spread | `rr25_7d - rr25_30d`, `rr25_30d - rr25_90d`, `rr25_7d - rr25_90d` |
| Tail Risk Pricing | BF Term Spread | `bf25_7d - bf25_30d`, `bf25_30d - bf25_90d`, `bf25_7d - bf25_90d` |

**Note**: Client-computed spreads do NOT have percentile values. The PCTL toggle is disabled for these charts. If you want percentiles on RR/BF spreads, add them as new metric keys to the backend pipeline and move them to the "Pre-computed spreads" section above.

## Key Components

### `SurfaceMetricChart` (`web/src/components/surface/SurfaceMetricChart.tsx`)

Reusable chart card component used by all 7 chart positions. Props:

| Prop | Type | Purpose |
|------|------|---------|
| `title` | string | Chart subtitle (e.g., "ATM Implied Volatility") |
| `options` | `{ label, key }[]` | Selectable metric options (tenor or spread pair) |
| `seriesMap` | `Map<string, MetricRow[]>` | All fetched series data |
| `latestMap` | `Map<string, MetricRow>` | Latest values per metric |
| `color` | string | Chart line color |
| `zeroline` | boolean | Show dashed line at y=0 (useful for spreads) |
| `valueLabel` | string | Label for value toggle button (default: "IV") |
| `spreadOptions` | `{ label, keyA, keyB }[]` | For client-computed spread mode |
| `spreadSeriesMap` | `Map<string, { ts, value }[]>` | Pre-computed spread series |
| `spreadLatestMap` | `Map<string, { value }>` | Pre-computed spread latest |

### Display Toggles

- **IV / PCTL**: Toggle between raw metric value and historical percentile rank
- **SPREAD / PCTL**: For pre-computed spreads (IV Term). PCTL available.
- **SPREAD only**: For client-computed spreads (RR/BF Term). PCTL disabled.

### Range Mapping

| Surface Range | Maps to TimeRange | Query behavior |
|---------------|-------------------|----------------|
| 1W | '5D' | Raw data, no downsampling |
| 1M | '1M' | Downsampled hourly (no effect for daily data) |
| 3M | '3M' | Downsampled daily (no effect for daily data) |

## What to Update If You Change Things

- **Add a new metric**: Add key to `METRIC_KEYS` in `constants.ts`, add to `ALL_METRIC_KEYS` array in `surface/page.tsx`, add a new `SurfaceMetricChart` instance, update this doc.
- **Add new tenor**: Add to the `options` array of the relevant `SurfaceMetricChart`.
- **Move client-computed spread to backend**: Add new metric key to pipeline, change the chart from `spreadOptions` mode to regular `options` mode with direct keys, update the tables above.
- **Change time ranges**: Update `RANGE_TO_TIME` mapping in `surface/page.tsx`.
- **Change chart colors**: Update the `color` prop on each `SurfaceMetricChart`.

## Files

| File | Purpose |
|------|---------|
| `web/src/app/surface/page.tsx` | Page layout, data fetching, spread computation |
| `web/src/components/surface/SurfaceMetricChart.tsx` | Reusable chart card component |
| `web/src/components/surface/IVHeatmap.tsx` | 3x3 IV heatmap (unchanged) |
| `web/src/lib/constants.ts` | Metric key constants |
| `web/src/lib/queries.ts` | Supabase query functions |
