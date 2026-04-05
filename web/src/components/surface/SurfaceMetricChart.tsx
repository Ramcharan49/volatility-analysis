'use client';

import { useState, useMemo } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import { getPercentileColor } from '@/lib/constants';
import type { MetricRow } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

type DisplayMode = 'value' | 'pctl';

interface MetricOption {
  label: string;
  key: string;
}

interface SpreadOption {
  label: string;
  keyA: string;
  keyB: string;
}

interface Props {
  title: string;
  /** Selectable metric options (e.g., tenor or spread pair) */
  options: MetricOption[];
  /** All fetched series data keyed by metric_key */
  seriesMap: Map<string, MetricRow[]>;
  /** Latest values keyed by metric_key */
  latestMap: Map<string, MetricRow>;
  /** Chart line color */
  color: string;
  /** Show zero reference line (useful for spreads) */
  zeroline?: boolean;
  /** Display toggle labels */
  valueLabel?: string;
  pctlLabel?: string;
  /** For client-computed spreads: provide pairs instead of direct keys */
  spreadOptions?: SpreadOption[];
  /** Computed spread series keyed by label */
  spreadSeriesMap?: Map<string, { ts: string; value: number }[]>;
  /** Computed spread latest keyed by label */
  spreadLatestMap?: Map<string, { value: number }>;
}

function parseTs(ts: string): number {
  return new Date(ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00')).getTime();
}

function buildOption(
  data: { time: number; value: number }[],
  color: string,
  zeroline: boolean,
  isPctl: boolean,
): EChartsCoreOption {
  return {
    grid: { top: 8, right: 12, bottom: 24, left: 48 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#1e293b' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#475569',
        fontSize: 9,
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
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#475569',
        fontSize: 9,
        fontFamily: 'var(--font-mono)',
        formatter: isPctl
          ? (v: number) => `${Math.round(v)}`
          : (v: number) => `${(v * 100).toFixed(1)}%`,
      },
      splitLine: { lineStyle: { color: '#111827', type: 'dashed' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      textStyle: { color: '#e5e7eb', fontSize: 11 },
      axisPointer: { lineStyle: { color: '#374151' } },
      formatter: (params: { value: [number, number] }[]) => {
        if (!params.length) return '';
        const [ts, val] = params[0].value;
        const d = new Date(ts);
        const dateStr = `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })} ${d.getFullYear()}`;
        const valStr = isPctl ? `${Math.round(val)}th %ile` : `${(val * 100).toFixed(2)}%`;
        return `<strong>${dateStr}</strong><br/>${valStr}`;
      },
    },
    series: [
      {
        type: 'line',
        data: data.map((d) => [d.time, d.value]),
        lineStyle: { color, width: 1.5 },
        itemStyle: { color },
        symbol: 'circle',
        symbolSize: 3,
        showSymbol: false,
        smooth: false,
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: `${color}18` },
              { offset: 1, color: `${color}02` },
            ],
          },
        },
      },
      // Zero reference line
      ...(zeroline
        ? [
            {
              type: 'line' as const,
              data: data.length > 0
                ? [[data[0].time, 0], [data[data.length - 1].time, 0]]
                : [],
              lineStyle: { color: '#374151', width: 1, type: 'dashed' as const },
              symbol: 'none' as const,
              z: 1,
            },
          ]
        : []),
    ],
  };
}

export default function SurfaceMetricChart({
  title,
  options,
  seriesMap,
  latestMap,
  color,
  zeroline = false,
  valueLabel = 'IV',
  pctlLabel = 'PCTL',
  spreadOptions,
  spreadSeriesMap,
  spreadLatestMap,
}: Props) {
  const isSpreadMode = !!spreadOptions;
  const selectorOptions = isSpreadMode
    ? spreadOptions!.map((s) => s.label)
    : options.map((o) => o.label);

  const [selectedIdx, setSelectedIdx] = useState(0);
  const [displayMode, setDisplayMode] = useState<DisplayMode>('value');

  // Get chart data based on selection and mode
  const chartData = useMemo(() => {
    if (isSpreadMode && spreadSeriesMap) {
      const label = spreadOptions![selectedIdx].label;
      const series = spreadSeriesMap.get(label) ?? [];
      if (displayMode === 'pctl') {
        // No percentile available for computed spreads
        return [];
      }
      return series.map((row) => ({
        time: parseTs(row.ts),
        value: row.value,
      }));
    }

    const key = options[selectedIdx]?.key;
    if (!key) return [];

    const rows = seriesMap.get(key) ?? [];
    return rows.map((row) => ({
      time: parseTs(row.ts),
      value:
        displayMode === 'pctl'
          ? (row.percentile != null ? Number(row.percentile) : 0)
          : (row.value != null ? Number(row.value) : 0),
    }));
  }, [isSpreadMode, spreadSeriesMap, spreadOptions, selectedIdx, displayMode, options, seriesMap]);

  // Get latest value
  const latestValue = useMemo(() => {
    if (isSpreadMode && spreadLatestMap) {
      const label = spreadOptions![selectedIdx].label;
      const latest = spreadLatestMap.get(label);
      return { value: latest?.value ?? null, percentile: null };
    }

    const key = options[selectedIdx]?.key;
    if (!key) return { value: null, percentile: null };

    const row = latestMap.get(key);
    return {
      value: row?.value != null ? Number(row.value) : null,
      percentile: row?.percentile != null ? Number(row.percentile) : null,
    };
  }, [isSpreadMode, spreadLatestMap, spreadOptions, selectedIdx, options, latestMap]);

  const pctlColor = getPercentileColor(latestValue.percentile);
  const isPctl = displayMode === 'pctl';
  // For computed spreads, disable PCTL toggle
  const canShowPctl = !isSpreadMode;

  return (
    <div className="card p-4">
      {/* Header row: selector + display toggle */}
      <div className="flex items-center justify-between mb-2">
        <div className="toggle-group">
          {selectorOptions.map((label, i) => (
            <button
              key={label}
              className={`toggle-btn ${selectedIdx === i ? 'active' : ''}`}
              onClick={() => setSelectedIdx(i)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="toggle-group">
          <button
            className={`toggle-btn ${displayMode === 'value' ? 'active' : ''}`}
            onClick={() => setDisplayMode('value')}
            style={displayMode === 'value' ? { background: color, color: '#fff', borderColor: color } : {}}
          >
            {valueLabel}
          </button>
          {canShowPctl && (
            <button
              className={`toggle-btn ${displayMode === 'pctl' ? 'active' : ''}`}
              onClick={() => setDisplayMode('pctl')}
            >
              {pctlLabel}
            </button>
          )}
        </div>
      </div>

      {/* Title + current value */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{title}</span>
        <div className="flex items-center gap-2">
          {latestValue.value != null && (
            <span
              className="mono-value text-lg font-semibold"
              style={{ color: isPctl ? '#9CA3AF' : pctlColor }}
            >
              {isPctl
                ? `${Math.round(latestValue.percentile ?? 0)}th`
                : `${(latestValue.value * 100).toFixed(2)}%`}
            </span>
          )}
          {latestValue.percentile != null && !isPctl && (
            <span
              className="mono-value text-xs px-1.5 py-0.5 rounded"
              style={{ color: pctlColor, background: `${pctlColor}15` }}
            >
              {Math.round(latestValue.percentile)}th
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 ? (
        <ChartContainer option={buildOption(chartData, color, zeroline, isPctl)} height="180px" />
      ) : (
        <div
          className="flex items-center justify-center"
          style={{ height: '180px', color: 'var(--text-faint)' }}
        >
          <span className="text-xs">
            {isPctl && isSpreadMode ? 'Percentile not available for computed spreads' : 'No data'}
          </span>
        </div>
      )}
    </div>
  );
}
