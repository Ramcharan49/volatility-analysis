'use client';

import ChartContainer from '@/components/shared/ChartContainer';
import { QUADRANT_CONFIG } from '@/lib/constants';
import type { RegimeTrailPoint } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

interface Props {
  stateScore: number | null;
  stressScore: number | null;
  trail: RegimeTrailPoint[];
}

const TRAIL_LABELS = ['2D ago', 'Yesterday', 'Today'];

export default function RegimeMap({ stateScore, stressScore, trail }: Props) {
  // Build scatter data: trail points + current
  const allPoints = [
    ...trail.map((p) => [p.state_score, p.stress_score]),
  ];
  // Add current if not already in trail
  if (stateScore != null && stressScore != null) {
    allPoints.push([stateScore, stressScore]);
  }

  // Only keep last 3
  const points = allPoints.slice(-3);
  const labels = TRAIL_LABELS.slice(-(points.length));

  const option: EChartsCoreOption = {
    grid: { top: 24, right: 24, bottom: 40, left: 48 },
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
      min: 0,
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
      formatter: (params: { dataIndex: number; value: number[] }) => {
        const idx = params.dataIndex;
        const lbl = labels[idx] ?? '';
        return `<strong>${lbl}</strong><br/>State: ${params.value[0]?.toFixed(1)}<br/>Stress: ${params.value[1]?.toFixed(1)}`;
      },
    },
    series: [
      // Quadrant backgrounds via markArea
      {
        type: 'scatter',
        data: [],
        markArea: {
          silent: true,
          data: [
            // Calm: bottom-left
            [
              { xAxis: 0, yAxis: 0, itemStyle: { color: QUADRANT_CONFIG.Calm.bg } },
              { xAxis: 50, yAxis: 50 },
            ],
            // Transition: bottom-right... actually top-left
            [
              { xAxis: 0, yAxis: 50, itemStyle: { color: QUADRANT_CONFIG.Transition.bg } },
              { xAxis: 50, yAxis: 100 },
            ],
            // Compression: top-left... actually bottom-right
            [
              { xAxis: 50, yAxis: 0, itemStyle: { color: QUADRANT_CONFIG.Compression.bg } },
              { xAxis: 100, yAxis: 50 },
            ],
            // Stress: top-right
            [
              { xAxis: 50, yAxis: 50, itemStyle: { color: QUADRANT_CONFIG.Stress.bg } },
              { xAxis: 100, yAxis: 100 },
            ],
          ],
        },
      },
      // Quadrant labels
      {
        type: 'scatter',
        data: [],
        markArea: { data: [] },
        markPoint: {
          silent: true,
          symbol: 'none',
          data: [
            { coord: [25, 25], name: 'Calm' },
            { coord: [25, 75], name: 'Transition' },
            { coord: [75, 25], name: 'Compression' },
            { coord: [75, 75], name: 'Stress' },
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
      // Trail line
      {
        type: 'line',
        data: points,
        lineStyle: { color: '#06b6d4', width: 1.5, type: 'dashed', opacity: 0.5 },
        symbol: 'none',
        z: 5,
      },
      // Trail points
      ...points.map((pt, i) => {
        const isLast = i === points.length - 1;
        return {
          type: 'scatter' as const,
          data: [pt],
          symbol: isLast ? 'circle' : 'emptyCircle',
          symbolSize: isLast ? 14 : 10,
          itemStyle: {
            color: isLast ? '#06b6d4' : 'transparent',
            borderColor: '#06b6d4',
            borderWidth: 2,
          },
          emphasis: {
            itemStyle: { shadowBlur: 12, shadowColor: 'rgba(6, 182, 212, 0.5)' },
          },
          z: 10,
          label: {
            show: true,
            position: 'top' as const,
            formatter: labels[i] ?? '',
            color: isLast ? '#06b6d4' : '#64748b',
            fontSize: 10,
            fontFamily: 'var(--font-display)',
            distance: 8,
          },
        };
      }),
      // Center crosshair lines
      {
        type: 'line',
        data: [[50, 0], [50, 100]],
        lineStyle: { color: '#1e293b', width: 1, type: 'dashed' },
        symbol: 'none',
        z: 1,
      },
      {
        type: 'line',
        data: [[0, 50], [100, 50]],
        lineStyle: { color: '#1e293b', width: 1, type: 'dashed' },
        symbol: 'none',
        z: 1,
      },
    ],
  };

  return (
    <div className="card p-4 animate-in stagger-1">
      <ChartContainer option={option} height="340px" />
    </div>
  );
}
