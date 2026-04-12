# Metric Tile Inline Expansion

## Problem

Clicking a metric tile on the Brief home page navigates to `/metric/[key]` — a full-page detail view. This breaks the "zero-scroll, single-screen arena" philosophy by forcing a hard page transition away from the bento dashboard. The user loses context of the RegimeMap and other tiles, and the interaction feels like a generic web page, not a premium instrument panel.

## Design: In-Place Tile Expansion

Each metric tile independently toggles between **compact** (current default) and **detailed** (expanded chart) modes when clicked. The 2x2 bento grid layout is unchanged — no tiles disappear, no grid reflows. Multiple tiles can be expanded simultaneously, enabling side-by-side comparison (e.g., Vol vs Skew).

### Three interaction states

**1. Compact (default)** — Existing tile layout: label, hero number, percentile rail, 44px sparkline, optional secondary reading. Hover lifts with spring physics. Click to expand.

**2. Detailed (expanded)** — Same tile footprint, different internal layout:
- Header compresses to one line: `VOL  0.20%  P88`
- Percentile rail removed (information is in the header badge)
- Sparkline replaced by an interactive time-series ECharts chart filling remaining space
- Chart has: time x-axis (minimal date labels), smooth line with area fill and neon glow, glass tooltip on hover
- Navigation pill(s) in the bottom-right corner: "Surface" and optionally "Flow"
- Click the tile header area again to collapse back to compact
- Spring-lift hover suppressed while expanded (tile is "pinned open")
- Border brightens slightly to indicate active/expanded state

**3. Deep navigation** — Clicking the "Surface" or "Flow" pill navigates to that page. Clicking the chart area itself could also navigate (to Surface as primary destination).

### Navigation mapping

| Metric key | Tile label | Surface pill | Flow pill |
|------------|-----------|-------------|----------|
| `atm_iv_30d` | Vol | `/surface` | `/flow` |
| `term_7d_30d` | Spread | `/surface` | (none) |
| `rr25_30d` | Skew | `/surface` | `/flow` |
| `bf25_30d` | Convexity | `/surface` | `/flow` |

### Design philosophy alignment

- **Zero-scroll mandate**: Grid stays fixed. No layout reflow, no page navigation.
- **Concealed complexity**: Sparkline teases → expanded chart reveals → full page deep-dives. Three levels of progressive disclosure.
- **Cross-pollinated systems**: HoverContext still works — hovering the expanded tile still triggers RegimeMap dimming.
- **Illusion of weight**: Spring-lift on compact, pinned-open state on expanded. Both feel physical.
- **Data as neon**: Expanded chart uses area fill + glow, matching sparkline aesthetic but larger and interactive.

## Data flow

Currently `page.tsx` processes `MetricRow[]` from `getMetricSeries()` into `number[]` (values only) for sparklines. The expanded chart needs timestamps for the x-axis.

Modify the existing `seriesByKey` memo to also build a `timeSeriesByKey: Map<string, { ts: string; value: number }[]>` map. The raw `MetricRow` already has `ts` and `value` fields. No new data fetching required — the expanded chart uses the same polled data.

## Components

### Modified: `MetricTile.tsx`
- Remove `Link` wrapper. Replace with a div that handles click-to-toggle.
- Add props: `expanded: boolean`, `onToggle: () => void`, `timeSeries: { ts: string; value: number }[]`
- Compact mode: current layout, unchanged
- Expanded mode: compressed single-line header → `MetricExpandedChart` → nav pills
- Use `AnimatePresence` for smooth transition between states
- Suppress `whileHover` spring-lift when expanded

### New: `MetricExpandedChart.tsx`
- Location: `web/src/components/brief/MetricExpandedChart.tsx`
- Props: `timeSeries`, `color`, `format`
- Renders ChartContainer with a time-series ECharts option:
  - `xAxis: { type: 'time' }` with minimal date labels (font-mono, 9px, ghost color)
  - Smooth line with area gradient fill and shadow glow
  - Glass tooltip (matching existing app tooltip style: dark bg, backdrop blur, frosted border)
  - "Now" dot at the last data point (matching sparkline's endpoint dot)
  - `animation: true` with subtle entrance
- Option is memoized with `useMemo`

### Modified: `page.tsx`
- Add `expandedKeys: Set<string>` state + toggle function
- Extend `seriesByKey` memo to also produce `timeSeriesByKey`
- Pass `expanded`, `onToggle`, `timeSeries` to each MetricTile

### No changes: `BentoGrid.tsx`, `Sparkline.tsx`, `ChartContainer.tsx`

## Critical files

| File | Action |
|------|--------|
| `web/src/components/brief/MetricTile.tsx` | Major refactor — remove Link, add expanded state rendering |
| `web/src/components/brief/MetricExpandedChart.tsx` | **New** — interactive time-series chart for expanded tile |
| `web/src/app/page.tsx` | Add expansion state + richer data passing |
| `web/src/app/globals.css` | Add `[data-expanded]` variant for glass-tile |

## Reused patterns

- `ChartContainer` init-once + merge-update (just shipped)
- `SurfaceMetricChart.buildOption()` pattern for time-series chart config (adapt, don't import)
- `parseTs()` timestamp parsing (exists in SurfaceMetricChart, will extract or duplicate)
- `getPercentileColor()`, `formatMetricValue()` — existing utilities
- Framer Motion `AnimatePresence`, `motion.div`, `layout` — already used throughout

## Verification

1. Click any tile → expands inline, chart renders with data
2. Click again → collapses back to sparkline view
3. Click multiple tiles → all expand independently, grid stays 2x2
4. Hover expanded tile → RegimeMap still dims (cross-pollination preserved)
5. Click "Surface" pill → navigates to `/surface`
6. Click "Flow" pill → navigates to `/flow` (only on Vol, Skew, Convexity tiles)
7. Polling updates → expanded chart merges new data without flash
8. `npx next build` → zero errors
