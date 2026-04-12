'use client';

import Link from 'next/link';
import ChartContainer from '@/components/shared/ChartContainer';
import PercentileBar from '@/components/shared/PercentileBar';
import StatsGrid from './StatsGrid';
import RelatedTenors from './RelatedTenors';
import { formatMetricValue, getPercentileColor } from '@/lib/formatting';
import { useMetricDetail } from '@/hooks/useMetricDetail';
import type { EChartsCoreOption } from 'echarts/core';

interface Props {
  metricKey: string;
}

function parseTs(ts: string): number {
  return new Date(ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00')).getTime();
}

export default function MetricDetailView({ metricKey }: Props) {
  const {
    meta, series, currentRow, latestMap,
    loading, timeRange, setTimeRange,
  } = useMetricDetail(metricKey);

  const value = currentRow?.value != null ? Number(currentRow.value) : null;
  const pct = currentRow?.percentile != null ? Number(currentRow.percentile) : null;
  const pctColor = getPercentileColor(pct);

  // Build chart option
  const chartData = series.map((row) => [parseTs(row.ts), Number(row.value ?? 0)]);

  const chartOption: EChartsCoreOption = {
    grid: { top: 8, right: 8, bottom: 24, left: 8, containLabel: false },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#111' } },
      axisTick: { show: false },
      axisLabel: { color: '#333', fontSize: 7, fontFamily: 'var(--font-mono)' },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      position: 'right',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        inside: true,
        color: '#333',
        fontSize: 7,
        fontFamily: 'var(--font-mono)',
        formatter: (v: number) => meta.format === 'pct' ? `${(v * 100).toFixed(1)}%` : v.toFixed(2),
      },
      splitLine: { lineStyle: { color: '#111', type: 'dashed' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(26, 26, 26, 0.95)',
      borderColor: '#333',
      textStyle: { color: '#ccc', fontSize: 11 },
    },
    series: [{
      type: 'line',
      data: chartData,
      lineStyle: { color: meta.color, width: 1.5 },
      itemStyle: { color: meta.color },
      symbol: 'none',
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: `${meta.color}15` },
            { offset: 1, color: `${meta.color}00` },
          ],
        },
      },
    }],
  };

  // Compute stats for the grid
  const values = series.map((r) => Number(r.value ?? 0));
  const high1m = values.length > 0 ? Math.max(...values) : null;
  const low1m = values.length > 0 ? Math.min(...values) : null;

  const statsItems = [
    { label: '1D Change', value: '--', color: 'var(--text-muted)' },
    { label: '5D Change', value: '--', color: 'var(--text-muted)' },
    {
      label: `${timeRange} High`,
      value: formatMetricValue(high1m, meta.format),
    },
    {
      label: `${timeRange} Low`,
      value: formatMetricValue(low1m, meta.format),
    },
  ];

  const ranges: ('1D' | '5D' | '1M' | '3M')[] = ['1D', '5D', '1M', '3M'];

  return (
    <div className="max-w-4xl mx-auto px-6 py-4 flex flex-col gap-3 page-enter">
      {/* Back nav */}
      <div className="flex items-center" style={{ padding: '4px 0' }}>
        <Link href="/" className="flex items-center gap-1.5">
          <span style={{ color: 'var(--accent-cyan)', fontSize: 14 }}>&lsaquo;</span>
          <span className="text-xs" style={{ color: 'var(--accent-cyan)' }}>Home</span>
        </Link>
      </div>

      {/* 2-column desktop layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: hero + chart */}
        <div className="lg:col-span-3 flex flex-col gap-3">
          {/* Hero row */}
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)', letterSpacing: '1px' }}>
                {meta.displayName} {meta.tenor ? `\u00B7 ${meta.tenor.toUpperCase()}` : ''}
              </div>
              <div className="flex items-baseline gap-2 mt-0.5">
                <span className="mono-value font-bold" style={{ fontSize: 'var(--font-size-hero)', color: 'var(--text-primary)', lineHeight: 1 }}>
                  {formatMetricValue(value, meta.format)}
                </span>
              </div>
            </div>
            <div className="text-right pb-1">
              <div className="mono-value text-xl font-semibold" style={{ color: pctColor, lineHeight: 1 }}>
                P{pct != null ? Math.round(pct) : '--'}
              </div>
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-faint)' }}>
                {pct != null ? (pct < 40 ? 'Below avg' : pct < 60 ? 'Normal' : pct < 80 ? 'Elevated' : 'High') : ''}
              </div>
            </div>
          </div>

          {/* Percentile bar */}
          <PercentileBar percentile={pct} />

          {/* Chart */}
          <ChartContainer option={chartOption} height="280px" />

          {/* Time range pills */}
          <div className="pill-group" style={{ paddingBottom: 'var(--space-xs)' }}>
            {ranges.map((r) => (
              <button
                key={r}
                className={`pill-btn ${timeRange === r ? 'active' : ''}`}
                onClick={() => setTimeRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* Right: stats + related + explainer */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <StatsGrid items={statsItems} />

          <RelatedTenors relatedKeys={meta.relatedKeys} latestMap={latestMap} />

          {meta.explainer && (
            <details className="card-dense" style={{ padding: '10px 14px' }}>
              <summary className="text-[11px] cursor-pointer" style={{ color: 'var(--text-muted)' }}>
                What is {meta.shortName}?
              </summary>
              <p className="text-[13px] mt-2 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                {meta.explainer}
              </p>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
