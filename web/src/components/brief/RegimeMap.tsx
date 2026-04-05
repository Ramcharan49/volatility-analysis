'use client';

import { useState, useCallback, useMemo } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import { QUADRANT_CONFIG } from '@/lib/constants';
import { getRegimeTrail } from '@/lib/queries';
import { usePolling } from '@/hooks/usePolling';
import type { RegimeTrailPoint } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

type TrailRange = '7D' | '1M' | '3M' | '1Y';

const RANGE_DAYS: Record<TrailRange, number> = {
  '7D': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
};

// How many recent days to show as the bright connected trail
const RECENT_TRAIL_DAYS = 7;

interface Props {
  stateScore: number | null;
  stressScore: number | null;
  trail: RegimeTrailPoint[]; // initial 7D trail from parent
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
}

export default function RegimeMap({ stateScore, stressScore, trail: initialTrail }: Props) {
  const [range, setRange] = useState<TrailRange>('7D');

  // Fetch extended trail when range > 7D
  const fetchExtended = useCallback(async () => {
    if (range === '7D') return null;
    return getRegimeTrail(RANGE_DAYS[range]);
  }, [range]);

  const { data: extendedTrail } = usePolling<RegimeTrailPoint[]>(fetchExtended, 120_000);

  // Use extended trail when available, otherwise initial 7D
  const fullTrail = range === '7D' ? initialTrail : (extendedTrail ?? initialTrail);

  // Deduplicate: don't add current scores if they match the latest trail point
  const trail = useMemo(() => {
    const pts = [...fullTrail];
    if (stateScore != null && stressScore != null) {
      const last = pts[pts.length - 1];
      if (!last || last.state_score !== stateScore || last.stress_score !== stressScore) {
        pts.push({ date: 'today', state_score: stateScore, stress_score: stressScore });
      }
    }
    return pts;
  }, [fullTrail, stateScore, stressScore]);

  // Split into recent trail (last 7) and historical cloud (everything before)
  const recentCount = Math.min(RECENT_TRAIL_DAYS, trail.length);
  const recentTrail = trail.slice(-recentCount);
  const historicalCloud = trail.length > recentCount ? trail.slice(0, -recentCount) : [];

  const recentPoints = recentTrail.map((p) => [p.state_score, p.stress_score]);
  const recentDates = recentTrail.map((p) => formatDate(p.date));

  const option: EChartsCoreOption = {
    grid: { top: 12, right: 24, bottom: 40, left: 48 },
    xAxis: {
      name: 'Surface State',
      nameLocation: 'center',
      nameGap: 28,
      nameTextStyle: { color: '#64748b', fontSize: 11, fontFamily: 'var(--font-display)' },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-mono)' },
      splitLine: { show: true, lineStyle: { color: '#111827', type: 'dashed' } },
    },
    yAxis: {
      name: 'Surface Stress',
      nameLocation: 'center',
      nameGap: 36,
      nameTextStyle: { color: '#64748b', fontSize: 11, fontFamily: 'var(--font-display)' },
      min: -100,
      max: 100,
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-mono)' },
      splitLine: { show: true, lineStyle: { color: '#111827', type: 'dashed' } },
    },
    tooltip: {
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#e5e7eb', fontSize: 12 },
    },
    series: [
      // Quadrant backgrounds
      {
        type: 'scatter',
        data: [],
        markArea: {
          silent: true,
          data: [
            [
              { xAxis: 0, yAxis: -100, itemStyle: { color: QUADRANT_CONFIG.Calm.bg } },
              { xAxis: 50, yAxis: 0 },
            ],
            [
              { xAxis: 0, yAxis: 0, itemStyle: { color: QUADRANT_CONFIG.Transition.bg } },
              { xAxis: 50, yAxis: 100 },
            ],
            [
              { xAxis: 50, yAxis: -100, itemStyle: { color: QUADRANT_CONFIG.Compression.bg } },
              { xAxis: 100, yAxis: 0 },
            ],
            [
              { xAxis: 50, yAxis: 0, itemStyle: { color: QUADRANT_CONFIG.Stress.bg } },
              { xAxis: 100, yAxis: 100 },
            ],
          ],
        },
      },
      // Quadrant labels
      {
        type: 'scatter',
        data: [],
        markPoint: {
          silent: true,
          symbol: 'none',
          data: [
            { coord: [25, -50], name: 'Calm' },
            { coord: [25, 50], name: 'Transition' },
            { coord: [75, -50], name: 'Compression' },
            { coord: [75, 50], name: 'Stress' },
          ],
          label: {
            show: true,
            fontSize: 10,
            fontWeight: 500,
            fontFamily: 'var(--font-display)',
            formatter: '{b}',
          },
          itemStyle: { color: 'transparent' },
        },
      },
      // Historical cloud (faded dots)
      ...(historicalCloud.length > 0
        ? [
            {
              type: 'scatter' as const,
              name: 'History',
              data: historicalCloud.map((p) => ({
                value: [p.state_score, p.stress_score],
                date: p.date,
              })),
              symbol: 'circle',
              symbolSize: 5,
              itemStyle: {
                color: '#475569',
                opacity: 0.15,
              },
              emphasis: {
                itemStyle: { opacity: 0.6, shadowBlur: 8, shadowColor: 'rgba(71, 85, 105, 0.5)' },
              },
              tooltip: {
                formatter: (params: { value: number[]; data: { date: string } }) =>
                  `<strong>${formatDate(params.data.date)}</strong><br/>State: ${params.value[0]?.toFixed(1)}<br/>Stress: ${params.value[1]?.toFixed(1)}`,
              },
              z: 2,
            },
          ]
        : []),
      // Recent trail line
      {
        type: 'line',
        data: recentPoints,
        lineStyle: { color: '#06b6d4', width: 1.5, type: 'dashed', opacity: 0.5 },
        symbol: 'none',
        z: 5,
      },
      // Recent trail points with date labels
      ...recentPoints.map((pt, i) => {
        const isLast = i === recentPoints.length - 1;
        const isFirst = i === 0;
        // Fade older points
        const opacity = 0.4 + 0.6 * (i / Math.max(recentPoints.length - 1, 1));
        return {
          type: 'scatter' as const,
          data: [pt],
          symbol: isLast ? 'circle' : 'emptyCircle',
          symbolSize: isLast ? 14 : 8 + (i / recentPoints.length) * 4,
          itemStyle: {
            color: isLast ? '#06b6d4' : 'transparent',
            borderColor: '#06b6d4',
            borderWidth: 2,
            opacity,
          },
          emphasis: {
            itemStyle: { shadowBlur: 12, shadowColor: 'rgba(6, 182, 212, 0.5)' },
          },
          z: 10,
          label: {
            show: isLast || isFirst || recentPoints.length <= 5,
            position: 'top' as const,
            formatter: recentDates[i] ?? '',
            color: isLast ? '#06b6d4' : '#64748b',
            fontSize: 9,
            fontFamily: 'var(--font-display)',
            distance: 8,
          },
          tooltip: {
            formatter: () =>
              `<strong>${recentDates[i]}</strong><br/>State: ${(pt as number[])[0]?.toFixed(1)}<br/>Stress: ${(pt as number[])[1]?.toFixed(1)}`,
          },
        };
      }),
      // Crosshair lines
      {
        type: 'line',
        data: [[50, -100], [50, 100]],
        lineStyle: { color: '#1e293b', width: 1, type: 'dashed' },
        symbol: 'none',
        z: 1,
      },
      {
        type: 'line',
        data: [[0, 0], [100, 0]],
        lineStyle: { color: '#1e293b', width: 1, type: 'dashed' },
        symbol: 'none',
        z: 1,
      },
    ],
  };

  return (
    <div className="card p-4 animate-in stagger-1">
      {/* Range selector */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-medium" style={{ color: 'var(--text-faint)' }}>Trail</span>
        <div className="toggle-group">
          {(['7D', '1M', '3M', '1Y'] as TrailRange[]).map((r) => (
            <button
              key={r}
              className={`toggle-btn ${range === r ? 'active' : ''}`}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <ChartContainer option={option} height="320px" />
    </div>
  );
}
