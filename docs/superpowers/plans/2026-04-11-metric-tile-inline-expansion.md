# Metric Tile Inline Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the metric tile click-to-navigate behavior with an in-place expand/collapse that reveals an interactive time-series chart, with navigation pills to Surface/Flow pages.

**Architecture:** Each MetricTile independently toggles between compact (sparkline) and detailed (interactive chart) modes. The 2x2 BentoGrid layout is unchanged. A new `MetricExpandedChart` component renders the time-series via ChartContainer. The home page manages expansion state and passes richer time-series data (with timestamps) to tiles.

**Tech Stack:** Next.js 16 + React 19, Framer Motion (AnimatePresence, layout), ECharts via ChartContainer, Tailwind CSS v4

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `web/src/components/brief/MetricExpandedChart.tsx` | **Create** | Interactive time-series chart for expanded tile state |
| `web/src/components/brief/MetricTile.tsx` | **Modify** | Toggle compact/detailed modes, remove Link navigation |
| `web/src/app/page.tsx` | **Modify** | Expansion state management, richer data passing |
| `web/src/app/globals.css` | **Modify** | `[data-expanded]` styling for glass-tile |

---

### Task 1: Create MetricExpandedChart component

**Files:**
- Create: `web/src/components/brief/MetricExpandedChart.tsx`

This component renders an interactive time-series ECharts chart inside an expanded metric tile. It adapts the chart pattern from `SurfaceMetricChart.tsx` but is designed for the constrained tile footprint (~150px height).

- [ ] **Step 1: Create the component file**

Create `web/src/components/brief/MetricExpandedChart.tsx`:

```tsx
'use client';

import { useMemo } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import type { EChartsCoreOption } from 'echarts/core';
import type { MetricFormat } from '@/types';

interface Props {
  timeSeries: { ts: string; value: number }[];
  color: string;
  format: MetricFormat;
}

function parseTs(ts: string): number {
  return new Date(ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00')).getTime();
}

function formatValue(v: number, format: MetricFormat): string {
  switch (format) {
    case 'pct':
      return `${v.toFixed(2)}%`;
    case 'raw':
    default:
      return v.toFixed(2);
  }
}

export default function MetricExpandedChart({ timeSeries, color, format }: Props) {
  const option = useMemo<EChartsCoreOption>(() => {
    const data = timeSeries.map((d) => [parseTs(d.ts), d.value]);
    const lastPoint = data.length > 0 ? data[data.length - 1] : null;

    return {
      animation: true,
      animationDuration: 400,
      animationEasing: 'cubicOut',
      grid: { top: 6, right: 8, bottom: 20, left: 6, containLabel: false },
      xAxis: {
        type: 'time',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: 'var(--text-ghost)',
          fontSize: 8,
          fontFamily: 'var(--font-mono)',
          formatter: (value: number) => {
            const d = new Date(value);
            return `${d.getDate()}/${d.getMonth() + 1}`;
          },
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        show: false,
        scale: true,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(10, 10, 13, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.08)',
        borderWidth: 1,
        padding: [6, 10],
        textStyle: { color: '#f5f5f7', fontSize: 10, fontFamily: 'var(--font-mono)' },
        extraCssText:
          'backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); box-shadow: 0 8px 32px rgba(0,0,0,0.5);',
        axisPointer: { lineStyle: { color: 'rgba(255, 255, 255, 0.08)' } },
        formatter: (params: { value: [number, number] }[]) => {
          if (!params.length) return '';
          const [ts, val] = params[0].value;
          const d = new Date(ts);
          const dateStr = `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
          return `<strong>${dateStr}</strong><br/>${formatValue(val, format)}`;
        },
      },
      series: [
        {
          type: 'line',
          data,
          smooth: 0.35,
          symbol: 'none',
          lineStyle: {
            color,
            width: 1.6,
            shadowColor: color,
            shadowBlur: 10,
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: `${color}33` },
                { offset: 1, color: `${color}00` },
              ],
            },
          },
          emphasis: { disabled: true },
          z: 2,
        },
        // "Now" dot at the last data point
        ...(lastPoint
          ? [
              {
                type: 'scatter' as const,
                data: [lastPoint],
                symbol: 'circle',
                symbolSize: 5,
                itemStyle: {
                  color,
                  shadowColor: color,
                  shadowBlur: 12,
                },
                silent: true,
                z: 4,
              },
            ]
          : []),
      ],
    };
  }, [timeSeries, color, format]);

  if (!timeSeries || timeSeries.length === 0) {
    return <div className="flex-1" />;
  }

  return <ChartContainer option={option} height="100%" className="flex-1 min-h-0" />;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd web && npx next build 2>&1 | tail -5`

Expected: Build succeeds (component is not imported yet, but should compile without type errors if everything is correct). Since it's unused, it may be tree-shaken — the key test is no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/brief/MetricExpandedChart.tsx
git commit -m "feat(brief): add MetricExpandedChart component for tile expansion"
```

---

### Task 2: Add expanded glass-tile CSS variant

**Files:**
- Modify: `web/src/app/globals.css` (inside the `.glass-tile` rule block)

When a tile has `data-expanded="true"`, it should show a brighter border and subtle glow to indicate it's pinned open, and the CSS `:hover` transform should be suppressed (the Framer Motion spring-lift will also be suppressed in Task 3).

- [ ] **Step 1: Read the current glass-tile CSS to find the right insertion point**

Read `web/src/app/globals.css` and locate the `.glass-tile` block. Find the existing `[data-regime-hovered="true"]` rule — the expanded variant goes right after it.

- [ ] **Step 2: Add the `[data-expanded]` CSS rules**

After the existing `.glass-tile[data-regime-hovered="true"]` rule block, add:

```css
.glass-tile[data-expanded="true"] {
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-hover);
  box-shadow: var(--glass-shadow-hover);
}
.glass-tile[data-expanded="true"]:hover {
  transform: none;
}
```

This gives the expanded tile the same visual treatment as hover (brighter border, slightly more luminous surface) but locks it in permanently. The `:hover` transform override prevents the CSS-level `translateY(-2px)` from fighting with Framer Motion.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/globals.css
git commit -m "style(brief): add data-expanded glass-tile variant"
```

---

### Task 3: Refactor MetricTile for expand/collapse

**Files:**
- Modify: `web/src/components/brief/MetricTile.tsx`

This is the main refactor. The tile switches from a `Link`-based navigation component to a toggle component with two internal layout states.

- [ ] **Step 1: Update imports**

Replace the import section (lines 1-10):

```tsx
'use client';

import Link from 'next/link';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import Sparkline from './Sparkline';
import MetricExpandedChart from './MetricExpandedChart';
import CountUpNumber from './CountUpNumber';
import { getPercentileColor, getMetricMeta } from '@/lib/constants';
import { formatMetricValue } from '@/lib/formatting';
import { useHover } from './HoverContext';
import type { MetricFormat } from '@/types';
```

Note: `Link` is still imported — it's used for the navigation pills inside the expanded view.

- [ ] **Step 2: Update the Props interface**

Replace the `Props` interface (lines 17-25) with:

```tsx
interface Props {
  metricKey: string;
  label: string;
  value: number | null;
  format: MetricFormat;
  percentile: number | null;
  series: number[];
  secondary?: SecondaryReading;
  expanded?: boolean;
  onToggle?: () => void;
  timeSeries?: { ts: string; value: number }[];
}
```

- [ ] **Step 3: Rewrite the component body**

Replace the entire component function (from `export default function MetricTile` through the end of the file) with:

```tsx
export default function MetricTile({
  metricKey,
  label,
  value,
  format,
  percentile,
  series,
  secondary,
  expanded = false,
  onToggle,
  timeSeries,
}: Props) {
  const pctColor = getPercentileColor(percentile);
  const pctText = percentile != null ? `P${Math.round(percentile)}` : '--';
  const railPosition = percentile != null ? Math.max(0, Math.min(100, percentile)) : null;

  const { setHovered, regimeHovered } = useHover();
  const meta = getMetricMeta(metricKey);

  const handleHoverStart = () => {
    setHovered({
      key: metricKey,
      displayName: meta.displayName,
      valueText: formatMetricValue(value, format),
      percentile,
      color: pctColor,
    });
  };
  const handleHoverEnd = () => setHovered(null);

  // Determine which deep-dive pages this metric maps to
  const hasFlow = meta.family !== 'term';

  return (
    <motion.div
      variants={itemVariants}
      whileHover={
        expanded
          ? undefined
          : {
              y: -3,
              scale: 1.012,
              transition: { type: 'spring', stiffness: 380, damping: 26 },
            }
      }
      onHoverStart={handleHoverStart}
      onHoverEnd={handleHoverEnd}
      className="min-h-0"
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle?.();
          }
        }}
        className="glass-tile group relative flex flex-col justify-between p-5 min-h-0 h-full"
        data-regime-hovered={regimeHovered ? 'true' : undefined}
        data-expanded={expanded ? 'true' : undefined}
        style={{ cursor: 'pointer' }}
      >
        <AnimatePresence mode="wait" initial={false}>
          {expanded ? (
            <motion.div
              key="detailed"
              className="flex flex-col h-full min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {/* Compact header — single line */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[10px] font-semibold tracking-[0.2em] uppercase"
                    style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                  >
                    {label}
                  </span>
                  <span
                    className="text-hero text-[14px]"
                    style={{ fontWeight: 600 }}
                  >
                    {formatMetricValue(value, format)}
                  </span>
                </div>
                <span
                  className="mono-value text-[10px] font-semibold tracking-[0.1em]"
                  style={{ color: pctColor }}
                >
                  {pctText}
                </span>
              </div>

              {/* Interactive chart — fills remaining space */}
              <div
                className="flex-1 min-h-0"
                onClick={(e) => e.stopPropagation()}
              >
                <MetricExpandedChart
                  timeSeries={timeSeries ?? []}
                  color={pctColor}
                  format={format}
                />
              </div>

              {/* Navigation pills */}
              <div
                className="flex items-center justify-end gap-2 mt-2"
                onClick={(e) => e.stopPropagation()}
              >
                <Link
                  href="/surface"
                  className="text-[9px] font-semibold tracking-[0.15em] uppercase px-2.5 py-1 rounded-full transition-colors duration-150"
                  style={{
                    fontFamily: 'var(--font-label)',
                    color: 'var(--text-muted)',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  Surface
                </Link>
                {hasFlow && (
                  <Link
                    href="/flow"
                    className="text-[9px] font-semibold tracking-[0.15em] uppercase px-2.5 py-1 rounded-full transition-colors duration-150"
                    style={{
                      fontFamily: 'var(--font-label)',
                      color: 'var(--text-muted)',
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                    }}
                  >
                    Flow
                  </Link>
                )}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="compact"
              className="flex flex-col justify-between h-full"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {/* Category label */}
              <div className="flex items-center justify-between">
                <span
                  className="text-[10px] font-semibold tracking-[0.2em] uppercase"
                  style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                >
                  {label}
                </span>
                <span
                  className="mono-value text-[11px] font-semibold tracking-[0.1em]"
                  style={{ color: pctColor }}
                >
                  {pctText}
                </span>
              </div>

              {/* Hero number */}
              <div className="flex items-baseline gap-2 mt-2">
                <CountUpNumber
                  value={value}
                  format={format}
                  className="text-hero"
                  style={{ fontSize: 'clamp(30px, 3.4vw, 48px)', fontWeight: 600 }}
                />
              </div>

              {/* Percentile rail */}
              <div className="relative mt-3 h-[2px] w-full" aria-hidden="true">
                <div
                  className="absolute inset-0 rounded-full"
                  style={{ background: 'rgba(255, 255, 255, 0.05)' }}
                />
                {railPosition != null && (
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full"
                    style={{
                      left: `${railPosition}%`,
                      transform: 'translate(-50%, -50%)',
                      background: pctColor,
                      boxShadow: `0 0 6px ${pctColor}, 0 0 2px ${pctColor}`,
                    }}
                  />
                )}
              </div>

              {/* Sparkline */}
              <div className="mt-3 flex-1 min-h-0" style={{ color: pctColor }}>
                <Sparkline data={series} color={pctColor} height={44} />
              </div>

              {/* Secondary reading */}
              {secondary && (
                <div className="flex items-center gap-1.5 mt-2">
                  <span
                    className="text-[9px] tracking-[0.2em] uppercase font-semibold"
                    style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                  >
                    {secondary.label}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--text-ghost)' }}>
                    ·
                  </span>
                  <span
                    className="mono-value text-[10px] font-semibold"
                    style={{ color: getPercentileColor(secondary.percentile) }}
                  >
                    {secondary.percentile != null ? `P${Math.round(secondary.percentile)}` : '--'}
                  </span>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
```

Key decisions in this code:
- `Link` is removed from the outer wrapper — the div with `role="button"` handles click-to-toggle
- `onClick={(e) => e.stopPropagation()}` on the chart area and nav pills prevents the tile toggle from firing when interacting with the chart or clicking a navigation link
- `whileHover` is set to `undefined` when expanded — no spring-lift on a pinned tile
- `AnimatePresence mode="wait"` cross-fades between compact and detailed states
- `hasFlow` is derived from `meta.family !== 'term'` — the term spread metric only lives on Surface
- Padding reduced from `p-6` to `p-5` in expanded mode to give the chart more room

- [ ] **Step 4: Verify it compiles**

Run: `cd web && npx next build 2>&1 | tail -5`

Expected: TypeScript error — `page.tsx` is still passing old props. That's expected; we fix it in Task 4.

- [ ] **Step 5: Commit (WIP)**

```bash
git add web/src/components/brief/MetricTile.tsx
git commit -m "feat(brief): refactor MetricTile for expand/collapse with chart"
```

---

### Task 4: Wire up expansion state in page.tsx

**Files:**
- Modify: `web/src/app/page.tsx`

This task connects everything: expansion state management and richer data passing.

- [ ] **Step 1: Add expansion state and time-series data**

In `page.tsx`, after the existing `const [summaryOpen, setSummaryOpen] = useState(false);` line (line 38), add:

```tsx
const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

const toggleExpanded = useCallback((key: string) => {
  setExpandedKeys((prev) => {
    const next = new Set(prev);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    return next;
  });
}, []);
```

- [ ] **Step 2: Extend the data memo to include time-series with timestamps**

Replace the `seriesByKey` memo (lines 40-56) with:

```tsx
const { seriesByKey, cardByKey, timeSeriesByKey } = useMemo(() => {
  const byKey = new Map<string, number[]>();
  const tsByKey = new Map<string, { ts: string; value: number }[]>();
  for (const row of data?.series ?? []) {
    if (row.value == null) continue;
    const val = Number(row.value);
    const arr = byKey.get(row.metric_key) ?? [];
    arr.push(val);
    byKey.set(row.metric_key, arr);
    const tsArr = tsByKey.get(row.metric_key) ?? [];
    tsArr.push({ ts: row.ts, value: val });
    tsByKey.set(row.metric_key, tsArr);
  }
  const cards = new Map<string, { value: number | null; percentile: number | null }>();
  for (const card of data?.dashboard?.key_cards_json ?? []) {
    cards.set(card.metric_key, {
      value: card.raw_value != null ? Number(card.raw_value) : null,
      percentile: card.percentile != null ? Number(card.percentile) : null,
    });
  }
  return { seriesByKey: byKey, cardByKey: cards, timeSeriesByKey: tsByKey };
}, [data]);
```

- [ ] **Step 3: Update tileFor helper to pass new props**

Replace the `tileFor` function (lines 70-90) with:

```tsx
const tileFor = (key: string, label: string, secondary?: { key: string; label: string }) => {
  const meta = getMetricMeta(key);
  const card = cardByKey.get(key);
  const secondaryCard = secondary ? cardByKey.get(secondary.key) : undefined;
  return (
    <MetricTile
      key={key}
      metricKey={key}
      label={label}
      value={card?.value ?? null}
      format={meta.format}
      percentile={card?.percentile ?? null}
      series={seriesByKey.get(key) ?? []}
      expanded={expandedKeys.has(key)}
      onToggle={() => toggleExpanded(key)}
      timeSeries={timeSeriesByKey.get(key) ?? []}
      secondary={
        secondary && secondaryCard
          ? { label: secondary.label, percentile: secondaryCard.percentile }
          : undefined
      }
    />
  );
};
```

- [ ] **Step 4: Update useState import**

The import line (line 3) already has `useState`. Verify `useCallback` is also imported (it should be — it's used for `fetchHome`). The line should read:

```tsx
import { useCallback, useMemo, useState } from 'react';
```

This is already correct in the current file.

- [ ] **Step 5: Build and verify**

Run: `cd web && npx next build 2>&1 | tail -10`

Expected: Build succeeds — zero errors, zero TypeScript warnings.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/page.tsx
git commit -m "feat(brief): wire tile expansion state and time-series data"
```

---

### Task 5: Add expanded glass-tile CSS

**Files:**
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Find the glass-tile regime-hovered rule**

Read `web/src/app/globals.css` and search for `data-regime-hovered`. The expanded variant goes right after that rule block.

- [ ] **Step 2: Add the expanded CSS rules**

After the `.glass-tile[data-regime-hovered="true"]` block, add:

```css
.glass-tile[data-expanded="true"] {
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-hover);
  box-shadow: var(--glass-shadow-hover);
}
.glass-tile[data-expanded="true"]:hover {
  transform: none;
}
```

- [ ] **Step 3: Build and verify**

Run: `cd web && npx next build 2>&1 | tail -5`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/globals.css
git commit -m "style(brief): add data-expanded glass-tile CSS variant"
```

---

### Task 6: Visual verification

**Files:** None modified — this is testing only.

- [ ] **Step 1: Start the dev server**

Run: `cd web && npx next dev`

Open `http://localhost:3000` in the browser.

- [ ] **Step 2: Test compact state (default)**

Verify all 4 tiles display in their default compact layout: label, hero number, percentile rail, sparkline. Hover should spring-lift each tile. RegimeMap cross-pollination dimming should work when hovering tiles.

- [ ] **Step 3: Test single tile expansion**

Click the "Vol" tile. Verify:
- Header compresses to one line: `VOL  0.20%  P88`
- Interactive time-series chart appears with date x-axis, smooth line, area fill, and glow
- "Surface" and "Flow" navigation pills appear at bottom-right
- Tile border brightens (expanded state CSS)
- Hovering the expanded tile does NOT spring-lift
- Hovering the chart shows glass tooltip with date + value

- [ ] **Step 4: Test multi-tile expansion**

Click "Skew" tile while "Vol" is still expanded. Verify:
- Both tiles show expanded chart views side by side
- Grid stays 2x2 — no layout reflow
- Both charts are interactive independently

- [ ] **Step 5: Test collapse**

Click the "Vol" tile header area again. Verify:
- Tile smoothly transitions back to compact layout
- Sparkline reappears
- Hero number returns to large format
- "Skew" tile remains expanded (independent state)

- [ ] **Step 6: Test navigation pills**

Click "Surface" pill on any expanded tile. Verify it navigates to `/surface` (should return 200 after our earlier cache fix). Press back, click "Flow" pill — navigates to `/flow`.

Verify "Spread" tile (term_7d_30d) only shows "Surface" pill (no "Flow").

- [ ] **Step 7: Test cross-pollination still works**

Hover an expanded tile. Verify RegimeMap dims and shows the callout with metric name + value + percentile.

- [ ] **Step 8: Test polling updates**

Wait ~60 seconds (or during market hours). When data refreshes, the expanded chart should merge the new data point without flashing or replaying entrance animation (thanks to the init-once ChartContainer pattern).

- [ ] **Step 9: Check console for errors**

Open DevTools console. Verify no React warnings, no ECharts errors, no stale closure warnings.

- [ ] **Step 10: Commit verification notes**

No code to commit — all implementation was committed in Tasks 1-5.

---

## Self-Review Checklist

- **Spec coverage:** All items from the spec are covered:
  - [x] In-place expansion (Task 3)
  - [x] Multiple tiles open simultaneously (Task 4 — Set-based state)
  - [x] Interactive chart with glass tooltip (Task 1)
  - [x] Navigation pills to Surface/Flow (Task 3)
  - [x] term_7d_30d only gets Surface pill (Task 3 — `meta.family !== 'term'`)
  - [x] Cross-pollination preserved (Task 3 — HoverContext handlers unchanged)
  - [x] Expanded CSS variant (Task 5)
  - [x] Spring-lift suppressed when expanded (Task 3)
  - [x] Timestamp data flow (Task 4)

- **Placeholder scan:** No TBD/TODO in any step. All code blocks are complete.

- **Type consistency:**
  - `timeSeries: { ts: string; value: number }[]` — consistent across Props in MetricExpandedChart (Task 1), MetricTile (Task 3), and the `tsByKey` map in page.tsx (Task 4)
  - `expanded: boolean` / `onToggle: () => void` — consistent between MetricTile Props (Task 3) and page.tsx wiring (Task 4)
  - `MetricRow.ts` field is used for timestamps — confirmed from types/index.ts (line 46: `ts: string`)
