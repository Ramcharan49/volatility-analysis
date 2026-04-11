'use client';

import { useState, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import ChartContainer from '@/components/shared/ChartContainer';
import { QUADRANT_CONFIG } from '@/lib/constants';
import { getRegimeTrail } from '@/lib/queries';
import { usePolling } from '@/hooks/usePolling';
import type { Quadrant, RegimeTrailPoint } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

// ECharts grid insets — must match grid option below so the breath overlay
// can be positioned at the correct data coordinate.
const GRID_TOP = 36;
const GRID_RIGHT = 48;
const GRID_BOTTOM = 36;
const GRID_LEFT = 48;

type TrailRange = '7D' | '1M' | '3M' | '1Y';

const RANGE_DAYS: Record<TrailRange, number> = {
  '7D': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
};

const RECENT_TRAIL_DAYS = 7;

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
  const [range] = useState<TrailRange>('1M');

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

  const accentColor = regimeConfig.color;
  const accentRgb = accentColor.replace('#', '');
  const accentR = parseInt(accentRgb.slice(0, 2), 16);
  const accentG = parseInt(accentRgb.slice(2, 4), 16);
  const accentB = parseInt(accentRgb.slice(4, 6), 16);
  const accentGlow = `rgba(${accentR}, ${accentG}, ${accentB}, 0.55)`;

  // Split recent trail into segments so each can have its own fading opacity → comet tail
  const trailSegments = recentPoints.length > 1
    ? recentPoints.slice(0, -1).map((pt, i) => {
        const next = recentPoints[i + 1];
        // Normalized position in trail: 0 = oldest, 1 = newest
        const t = i / Math.max(recentPoints.length - 2, 1);
        return {
          points: [pt, next] as number[][],
          opacity: 0.15 + 0.75 * t, // fades from 0.15 (old) → 0.90 (recent)
          width: 1.2 + 0.9 * t,      // thickens slightly toward present
        };
      })
    : [];

  const option: EChartsCoreOption = {
    animation: true,
    animationDuration: 800,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 400,
    animationEasingUpdate: 'cubicOut',
    grid: { top: GRID_TOP, right: GRID_RIGHT, bottom: GRID_BOTTOM, left: GRID_LEFT },
    xAxis: {
      min: 0,
      max: 100,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      min: -100,
      max: 100,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    tooltip: {
      backgroundColor: 'rgba(10, 10, 13, 0.85)',
      borderColor: 'rgba(255, 255, 255, 0.08)',
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: '#f5f5f7', fontSize: 11, fontFamily: 'var(--font-mono)' },
      extraCssText: 'backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); box-shadow: 0 8px 32px rgba(0,0,0,0.5);',
    },
    series: [
      // Center crosshair — faint structural reference without looking like a cage
      {
        type: 'line',
        data: [],
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: false },
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.06)',
            width: 1,
            type: 'solid',
          },
          data: [
            [{ coord: [50, -100] }, { coord: [50, 100] }],
            [{ coord: [0, 0] }, { coord: [100, 0] }],
          ],
        },
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
              symbolSize: 4,
              itemStyle: { color: '#6b7280', opacity: 0.06 },
              emphasis: {
                itemStyle: { opacity: 0.5, shadowBlur: 6, shadowColor: 'rgba(107, 114, 128, 0.5)' },
              },
              tooltip: {
                formatter: (params: { value: number[]; data: { date: string } }) =>
                  `<strong>${formatDate(params.data.date)}</strong><br/>State ${params.value[0]?.toFixed(1)} · Stress ${params.value[1]?.toFixed(1)}`,
              },
              z: 2,
            },
          ]
        : []),
      // Comet-tail trail: each segment has its own opacity, fading from old (faint) → recent (bright)
      ...trailSegments.map((seg) => ({
        type: 'line' as const,
        data: seg.points,
        smooth: 0.25,
        lineStyle: {
          color: accentColor,
          width: seg.width,
          opacity: seg.opacity,
          shadowColor: accentGlow,
          shadowBlur: 10 + seg.opacity * 8,
        },
        symbol: 'none',
        silent: true,
        z: 5,
      })),
      // Recent trail points (glowing dots, fading into time)
      ...recentPoints.map((pt, i) => {
        const isLast = i === recentPoints.length - 1;
        const opacity = 0.35 + 0.65 * (i / Math.max(recentPoints.length - 1, 1));
        return {
          type: 'scatter' as const,
          data: [pt],
          symbol: 'circle',
          symbolSize: isLast ? 14 : 5 + (i / recentPoints.length) * 3,
          itemStyle: {
            color: isLast ? accentColor : 'transparent',
            borderColor: accentColor,
            borderWidth: isLast ? 0 : 1.5,
            opacity,
            ...(isLast
              ? { shadowBlur: 24, shadowColor: accentGlow }
              : {}),
          },
          emphasis: {
            itemStyle: { shadowBlur: 18, shadowColor: accentGlow },
          },
          z: 10,
          tooltip: {
            formatter: () =>
              `<strong>${recentDates[i]}</strong><br/>State ${(pt as number[])[0]?.toFixed(1)} · Stress ${(pt as number[])[1]?.toFixed(1)}`,
          },
        };
      }),
      // Outer glow rings around current position
      ...(recentPoints.length > 0
        ? [
            {
              type: 'scatter' as const,
              data: [recentPoints[recentPoints.length - 1]],
              symbol: 'circle',
              symbolSize: 28,
              itemStyle: {
                color: 'transparent',
                borderColor: accentColor,
                borderWidth: 1,
                opacity: 0.35,
                shadowBlur: 16,
                shadowColor: accentGlow,
              },
              z: 9,
              silent: true,
            },
            {
              type: 'scatter' as const,
              data: [recentPoints[recentPoints.length - 1]],
              symbol: 'circle',
              symbolSize: 44,
              itemStyle: {
                color: 'transparent',
                borderColor: accentColor,
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

  // Compute pixel position of current regime dot within the chart plot area
  // so we can overlay a breath-pulse ring on it (purely CSS, no ECharts redraw).
  const breathDot = (() => {
    if (stateScore == null || stressScore == null) return null;
    const xPct = Math.max(0, Math.min(100, stateScore)) / 100;
    const yPct = (100 - Math.max(-100, Math.min(100, stressScore))) / 200;
    return {
      left: `calc(${GRID_LEFT}px + (100% - ${GRID_LEFT + GRID_RIGHT}px) * ${xPct})`,
      top: `calc(${GRID_TOP}px + (100% - ${GRID_TOP + GRID_BOTTOM}px) * ${yPct})`,
    };
  })();

  return (
    <motion.div
      className="glass-tile-static relative h-full min-h-0 p-5 overflow-hidden"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] as const }}
    >
      {/* Atmospheric quadrant gradients — wider, dissipating from corners into center */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `
            radial-gradient(ellipse 90% 80% at 0% 100%, rgba(52, 211, 153, 0.07), transparent 70%),
            radial-gradient(ellipse 90% 80% at 0% 0%, rgba(251, 191, 36, 0.06), transparent 70%),
            radial-gradient(ellipse 90% 80% at 100% 100%, rgba(96, 165, 250, 0.06), transparent 70%),
            radial-gradient(ellipse 90% 80% at 100% 0%, rgba(248, 113, 113, 0.07), transparent 70%)
          `,
        }}
      />

      {/* Regime label — absolute top-left */}
      <div className="absolute top-4 left-5 z-10 flex items-center gap-2">
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{
            background: regimeConfig.color,
            boxShadow: `0 0 10px ${regimeConfig.color}, 0 0 4px ${regimeConfig.color}`,
          }}
        />
        <span
          className="text-[10px] font-bold tracking-[0.2em] uppercase"
          style={{ fontFamily: 'var(--font-label)', color: regimeConfig.color }}
        >
          {regimeConfig.label}
        </span>
      </div>

      {/* Radar coordinate labels — anchored to axis extremities */}
      <div className="absolute inset-0 pointer-events-none z-10">
        {/* Top: RISING (along upper edge of chart grid) */}
        <span
          className="absolute text-[8px] tracking-[0.22em] uppercase font-semibold"
          style={{
            top: 14,
            left: '50%',
            transform: 'translateX(-50%)',
            color: 'var(--text-ghost)',
            fontFamily: 'var(--font-label)',
          }}
        >
          ↑ Rising
        </span>
        {/* Bottom: DECLINING */}
        <span
          className="absolute text-[8px] tracking-[0.22em] uppercase font-semibold"
          style={{
            bottom: 14,
            left: '50%',
            transform: 'translateX(-50%)',
            color: 'var(--text-ghost)',
            fontFamily: 'var(--font-label)',
          }}
        >
          ↓ Declining
        </span>
        {/* Left: LOW VOL — vertically centered, written horizontally */}
        <span
          className="absolute text-[8px] tracking-[0.22em] uppercase font-semibold"
          style={{
            top: '50%',
            left: 10,
            transform: 'translateY(-50%)',
            color: 'var(--text-ghost)',
            fontFamily: 'var(--font-label)',
          }}
        >
          ← Low
        </span>
        {/* Right: HIGH VOL */}
        <span
          className="absolute text-[8px] tracking-[0.22em] uppercase font-semibold"
          style={{
            top: '50%',
            right: 12,
            transform: 'translateY(-50%)',
            color: 'var(--text-ghost)',
            fontFamily: 'var(--font-label)',
          }}
        >
          High →
        </span>
      </div>

      {/* Chart */}
      <div className="relative h-full">
        <ChartContainer option={option} height="100%" />

        {/* Breathing pulse ring over the current regime dot */}
        {breathDot && (
          <div
            className="regime-breath-pulse pointer-events-none absolute rounded-full"
            style={{
              left: breathDot.left,
              top: breathDot.top,
              width: 44,
              height: 44,
              borderColor: accentColor,
              ['--breath-glow' as string]: accentGlow,
            }}
            aria-hidden="true"
          />
        )}
      </div>
    </motion.div>
  );
}
