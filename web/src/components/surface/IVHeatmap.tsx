'use client';

import { useState } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import { TENOR_LABELS, DELTA_LABELS, TENORS, DELTAS, getPercentileColor } from '@/lib/constants';
import type { SurfaceCell, TenorCode, DeltaBucket } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

interface Props {
  cells: SurfaceCell[];
}

type ViewMode = 'iv' | 'percentile';

function getCellValue(cells: SurfaceCell[], tenor: TenorCode, delta: DeltaBucket, mode: ViewMode): number | null {
  const cell = cells.find((c) => c.tenor_code === tenor && c.delta_bucket === delta);
  if (!cell) return null;
  return mode === 'iv' ? (cell.iv != null ? Number(cell.iv) : null) : (cell.iv_percentile != null ? Number(cell.iv_percentile) : null);
}

export default function IVHeatmap({ cells }: Props) {
  const [mode, setMode] = useState<ViewMode>('iv');

  // Build heatmap data: [colIndex, rowIndex, value]
  const heatmapData: [number, number, number | null][] = [];
  const reversedDeltas = [...DELTAS].reverse(); // P25 at top

  for (let row = 0; row < reversedDeltas.length; row++) {
    for (let col = 0; col < TENORS.length; col++) {
      const val = getCellValue(cells, TENORS[col], reversedDeltas[row], mode);
      heatmapData.push([col, row, val]);
    }
  }

  const minVal = mode === 'iv' ? 0.05 : 0;
  const maxVal = mode === 'iv' ? 0.50 : 100;

  const option: EChartsCoreOption = {
    grid: { top: 8, right: 80, bottom: 32, left: 72 },
    xAxis: {
      type: 'category',
      data: TENORS.map((t) => TENOR_LABELS[t]),
      axisLine: { lineStyle: { color: '#212121' } },
      axisTick: { show: false },
      axisLabel: { color: '#b9b9b9', fontSize: 11, fontFamily: 'var(--font-mono)' },
    },
    yAxis: {
      type: 'category',
      data: reversedDeltas.map((d) => DELTA_LABELS[d]),
      axisLine: { lineStyle: { color: '#212121' } },
      axisTick: { show: false },
      axisLabel: { color: '#b9b9b9', fontSize: 11, fontFamily: 'var(--font-display)' },
    },
    visualMap: {
      show: true,
      min: minVal,
      max: maxVal,
      orient: 'vertical',
      right: 0,
      top: 'center',
      itemHeight: 160,
      itemWidth: 10,
      textStyle: { color: '#797979', fontSize: 10, fontFamily: 'var(--font-mono)' },
      formatter: (val: number) => mode === 'iv' ? `${(val * 100).toFixed(0)}%` : `${val.toFixed(0)}`,
      inRange: {
        color: mode === 'iv'
          ? ['#1e3a5f', '#1e4d6e', '#2d6a4f', '#f59e0b', '#ef4444', '#dc2626']
          : ['#3b82f6', '#60a5fa', '#6b7280', '#9ca3af', '#f59e0b', '#ef4444', '#dc2626'],
      },
    },
    tooltip: {
      backgroundColor: 'rgba(33, 33, 33, 0.95)',
      borderColor: '#353535',
      textStyle: { color: '#ffffff', fontSize: 12 },
      formatter: (params: { value: [number, number, number | null] }) => {
        const [col, row, val] = params.value;
        const tenor = TENOR_LABELS[TENORS[col]];
        const delta = DELTA_LABELS[reversedDeltas[row]];
        if (val == null) return `${delta} × ${tenor}<br/><span style="color:#797979">No data</span>`;
        const formatted = mode === 'iv' ? `${(val * 100).toFixed(2)}%` : `${val.toFixed(1)}th`;
        return `${delta} × ${tenor}<br/><strong>${formatted}</strong>`;
      },
    },
    series: [
      {
        type: 'heatmap',
        data: heatmapData.map(([x, y, v]) => [x, y, v ?? '-']),
        itemStyle: {
          borderColor: 'var(--bg-card)',
          borderWidth: 3,
          borderRadius: 4,
        },
        label: {
          show: true,
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          fontWeight: 600,
          formatter: (params: { value: [number, number, number | string] }) => {
            const v = params.value[2];
            if (v === '-' || v == null) return '-.--';
            const num = Number(v);
            return mode === 'iv' ? `${(num * 100).toFixed(2)}%` : `${num.toFixed(0)}`;
          },
          color: '#ffffff',
        },
        emphasis: {
          itemStyle: { borderColor: '#0052ef', borderWidth: 2 },
        },
      },
    ],
  };

  return (
    <div className="card p-4 animate-in stagger-1">
      <div className="flex items-center justify-between mb-3">
        <span className="section-header">IV Surface — Delta vs Maturity</span>
        <div className="toggle-group">
          <button
            className={`toggle-btn ${mode === 'iv' ? 'active' : ''}`}
            onClick={() => setMode('iv')}
          >
            IV
          </button>
          <button
            className={`toggle-btn ${mode === 'percentile' ? 'active' : ''}`}
            onClick={() => setMode('percentile')}
          >
            %ile
          </button>
        </div>
      </div>
      <ChartContainer option={option} height="220px" />
    </div>
  );
}
