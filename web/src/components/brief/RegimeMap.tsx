'use client';

import { useState, useCallback, useMemo } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import { QUADRANT_CONFIG } from '@/lib/constants';
import { getRegimeTrail } from '@/lib/queries';
import { usePolling } from '@/hooks/usePolling';
import type { Quadrant, RegimeTrailPoint } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

type TrailRange = '7D' | '1M' | '3M' | '1Y';

const RANGE_DAYS: Record<TrailRange, number> = {
  '7D': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
};

const RECENT_TRAIL_DAYS = 7;

const QUADRANT_LEGEND: { key: Quadrant; desc: string }[] = [
  { key: 'Transition', desc: 'Low vol · Rising' },
  { key: 'Stress', desc: 'High vol · Rising' },
  { key: 'Calm', desc: 'Low vol · Declining' },
  { key: 'Compression', desc: 'High vol · Declining' },
];

interface Props {
  stateScore: number | null;
  stressScore: number | null;
  quadrant: string | null;
  trail: RegimeTrailPoint[];
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
}

export default function RegimeMap({ stateScore, stressScore, quadrant, trail: initialTrail }: Props) {
  const [range, setRange] = useState<TrailRange>('1M');

  const fetchExtended = useCallback(async () => {
    if (range === '7D') return null;
    return getRegimeTrail(RANGE_DAYS[range]);
  }, [range]);

  const { data: extendedTrail } = usePolling<RegimeTrailPoint[]>(fetchExtended, 120_000);

  const fullTrail = range === '7D' ? initialTrail : (extendedTrail ?? initialTrail);

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

  const recentCount = Math.min(RECENT_TRAIL_DAYS, trail.length);
  const recentTrail = trail.slice(-recentCount);
  const historicalCloud = trail.length > recentCount ? trail.slice(0, -recentCount) : [];

  const recentPoints = recentTrail.map((p) => [p.state_score, p.stress_score]);
  const recentDates = recentTrail.map((p) => formatDate(p.date));

  const q = (quadrant as Quadrant) ?? 'Calm';
  const regimeConfig = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  const option: EChartsCoreOption = {
    grid: { top: 16, right: 24, bottom: 44, left: 52 },
    xAxis: {
      name: 'SURFACE STATE → (Volatility Level)',
      nameLocation: 'center',
      nameGap: 30,
      nameTextStyle: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-label)', letterSpacing: 1 },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-mono)' },
      splitLine: { show: false },
    },
    yAxis: {
      name: 'SURFACE FLOW → (Volatility Change)',
      nameLocation: 'center',
      nameGap: 40,
      nameTextStyle: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-label)', letterSpacing: 1 },
      min: -100,
      max: 100,
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, fontFamily: 'var(--font-mono)' },
      splitLine: { show: false },
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
              itemStyle: { color: '#475569', opacity: 0.15 },
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
      // Recent trail points
      ...recentPoints.map((pt, i) => {
        const isLast = i === recentPoints.length - 1;
        const isFirst = i === 0;
        const opacity = 0.4 + 0.6 * (i / Math.max(recentPoints.length - 1, 1));
        return {
          type: 'scatter' as const,
          data: [pt],
          symbol: 'circle',
          symbolSize: isLast ? 12 : 6 + (i / recentPoints.length) * 4,
          itemStyle: {
            color: isLast ? '#06b6d4' : 'transparent',
            borderColor: '#06b6d4',
            borderWidth: isLast ? 3 : 2,
            opacity,
            ...(isLast
              ? { shadowBlur: 20, shadowColor: 'rgba(6, 182, 212, 0.6)' }
              : {}),
          },
          emphasis: {
            itemStyle: { shadowBlur: 16, shadowColor: 'rgba(6, 182, 212, 0.5)' },
          },
          z: 10,
          label: {
            show: isLast || isFirst || recentPoints.length <= 5,
            position: 'top' as const,
            formatter: recentDates[i] ?? '',
            color: isLast ? '#06b6d4' : '#64748b',
            fontSize: 9,
            fontFamily: 'var(--font-label)',
            distance: 10,
          },
          tooltip: {
            formatter: () =>
              `<strong>${recentDates[i]}</strong><br/>State: ${(pt as number[])[0]?.toFixed(1)}<br/>Stress: ${(pt as number[])[1]?.toFixed(1)}`,
          },
        };
      }),
      // Glow ring around current position
      ...(recentPoints.length > 0
        ? [
            {
              type: 'scatter' as const,
              data: [recentPoints[recentPoints.length - 1]],
              symbol: 'circle',
              symbolSize: 24,
              itemStyle: {
                color: 'transparent',
                borderColor: '#06b6d4',
                borderWidth: 1,
                opacity: 0.3,
              },
              z: 9,
              silent: true,
            },
            {
              type: 'scatter' as const,
              data: [recentPoints[recentPoints.length - 1]],
              symbol: 'circle',
              symbolSize: 36,
              itemStyle: {
                color: 'transparent',
                borderColor: '#06b6d4',
                borderWidth: 1,
                opacity: 0.12,
              },
              z: 8,
              silent: true,
            },
          ]
        : []),
    ],
  };

  return (
    <div className="card p-5 animate-in stagger-1">
      {/* Header row: title + trail selector + regime badge */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span
            className="text-xs font-semibold tracking-widest uppercase"
            style={{ fontFamily: 'var(--font-label)', color: 'var(--text-muted)' }}
          >
            Volatility Regime Indicator
          </span>
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
        {/* Regime badge */}
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-lg"
          style={{
            border: `1px solid ${regimeConfig.color}30`,
            background: regimeConfig.bg,
          }}
        >
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ background: regimeConfig.color, boxShadow: `0 0 8px ${regimeConfig.color}60` }}
          />
          <span
            className="text-sm font-bold tracking-wide uppercase"
            style={{ fontFamily: 'var(--font-label)', color: regimeConfig.color }}
          >
            {regimeConfig.label}
          </span>
        </div>
      </div>

      {/* Chart */}
      <ChartContainer option={option} height="380px" />

      {/* Bottom legend */}
      <div className="flex items-center justify-between mt-3 px-2">
        <div className="flex items-center gap-5">
          {QUADRANT_LEGEND.map(({ key, desc }) => {
            const cfg = QUADRANT_CONFIG[key];
            return (
              <div key={key} className="flex items-center gap-1.5">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: cfg.color }}
                />
                <span className="text-[0.65rem] font-medium uppercase tracking-wide" style={{ fontFamily: 'var(--font-label)', color: cfg.color }}>
                  {cfg.label}
                </span>
                <span className="text-[0.6rem]" style={{ color: 'var(--text-faint)' }}>
                  ({desc})
                </span>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="flex items-center gap-0.5">
              {[0.2, 0.4, 0.7, 1].map((op, i) => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: '#06b6d4', opacity: op }}
                />
              ))}
            </div>
            <span className="text-[0.6rem]" style={{ color: 'var(--text-faint)' }}>
              Historical trail
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: '#06b6d4', boxShadow: '0 0 6px rgba(6,182,212,0.5)' }}
            />
            <span className="text-[0.6rem]" style={{ color: 'var(--text-faint)' }}>
              Current regime
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
