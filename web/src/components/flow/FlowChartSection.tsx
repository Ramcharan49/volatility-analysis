'use client';

import ChartContainer from '@/components/shared/ChartContainer';
import PercentileValue from '@/components/shared/PercentileValue';
import SectionHeader from '@/components/shared/SectionHeader';
import { getPercentileColor, TENOR_LABELS } from '@/lib/constants';
import type { MetricRow, TenorCode } from '@/types';
import type { EChartsCoreOption } from 'echarts/core';

interface Props {
  title: string;
  subtitle?: string;
  /** Primary metric series (e.g., d_atm_iv_7d, d_atm_iv_30d) grouped by tenor */
  primarySeries: { tenor: TenorCode; label: string; data: MetricRow[] }[];
  /** Secondary (spread) series, if any */
  spreadSeries?: { label: string; data: MetricRow[] }[];
  /** Latest snapshot values for the right-side badges */
  latestPrimary: { label: string; value: number | null; percentile: number | null }[];
  latestSpread?: { label: string; value: number | null; percentile: number | null }[];
  staggerClass?: string;
}

const TENOR_COLORS: Record<TenorCode, string> = {
  '7d': '#0052ef',
  '30d': '#a78bfa',
  '90d': '#f59e0b',
};

const SPREAD_COLORS = ['#34d399', '#fb923c', '#f472b6'];

/** Convert Postgres timestamp (e.g. "2026-04-02 09:59:00+00") to epoch ms */
function parseTs(ts: string): number {
  return new Date(ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00')).getTime();
}

function buildLineOption(
  series: { label: string; color: string; data: { time: number; value: number }[] }[],
): EChartsCoreOption {
  return {
    grid: { top: 16, right: 12, bottom: 28, left: 52 },
    xAxis: {
      type: 'time',
      boundaryGap: ['2%', '8%'],
      maxInterval: 3600 * 24 * 1000 * 2,
      axisLine: { lineStyle: { color: '#212121' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#595959',
        fontSize: 9,
        fontFamily: 'var(--font-mono)',
        hideOverlap: true,
        formatter: (value: number) => {
          const d = new Date(value);
          const day = d.getDate();
          const mon = d.toLocaleString('en', { month: 'short' });
          return `${day} ${mon}`;
        },
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#595959',
        fontSize: 9,
        fontFamily: 'var(--font-mono)',
        formatter: (v: number) => `${(v * 100).toFixed(1)}%`,
      },
      splitLine: { lineStyle: { color: '#161616', type: 'dashed' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(33, 33, 33, 0.95)',
      borderColor: '#353535',
      textStyle: { color: '#ffffff', fontSize: 11 },
      axisPointer: { lineStyle: { color: '#353535' } },
    },
    legend: {
      show: series.length > 1,
      top: 0,
      right: 0,
      textStyle: { color: '#797979', fontSize: 10 },
      icon: 'roundRect',
      itemWidth: 12,
      itemHeight: 3,
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0,
        filterMode: 'filter',
      },
    ],
    series: series.map((s) => ({
      name: s.label,
      type: 'line',
      data: s.data.map((d) => [d.time, d.value]),
      lineStyle: { color: s.color, width: 1.5 },
      itemStyle: { color: s.color },
      symbol: 'circle',
      symbolSize: 4,
      showSymbol: true,
      smooth: false,
      endLabel: {
        show: true,
        formatter: (p: { value: [number, number] }) =>
          `${p.value[1] >= 0 ? '+' : ''}${(p.value[1] * 100).toFixed(2)}%`,
        color: s.color,
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        distance: 6,
      },
      markPoint: {
        symbol: 'circle',
        symbolSize: 9,
        itemStyle: { color: s.color, borderColor: '#0b0b0b', borderWidth: 2 },
        label: { show: false },
        data: [{ type: 'max', valueDim: 'x' }],
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: `${s.color}20` },
            { offset: 1, color: `${s.color}02` },
          ],
        },
      },
    })),
  };
}

export default function FlowChartSection({
  title,
  subtitle,
  primarySeries,
  spreadSeries,
  latestPrimary,
  latestSpread,
  staggerClass = '',
}: Props) {
  // Build primary chart data
  const primaryChartSeries = primarySeries.map((s) => ({
    label: TENOR_LABELS[s.tenor],
    color: TENOR_COLORS[s.tenor],
    data: s.data.map((row) => ({
      time: parseTs(row.ts),
      value: row.value != null ? Number(row.value) : 0,
    })),
  }));

  const spreadChartSeries = (spreadSeries ?? []).map((s, i) => ({
    label: s.label,
    color: SPREAD_COLORS[i % SPREAD_COLORS.length],
    data: s.data.map((row) => ({
      time: parseTs(row.ts),
      value: row.value != null ? Number(row.value) : 0,
    })),
  }));

  const hasSpreads = spreadChartSeries.length > 0;

  return (
    <div className={`animate-in ${staggerClass}`}>
      <SectionHeader title={title} subtitle={subtitle} />

      <div className={`grid gap-3 ${hasSpreads ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
        {/* Primary chart */}
        <div className="card p-3">
          <ChartContainer option={buildLineOption(primaryChartSeries)} height="220px" />
          <div className="flex items-center gap-4 px-2 pt-2">
            {latestPrimary.map((item) => (
              <div key={item.label} className="flex items-center gap-1.5">
                <span className="text-[0.65rem]" style={{ color: 'var(--text-faint)' }}>{item.label}</span>
                <PercentileValue
                  value={item.value}
                  percentile={item.percentile}
                  format="pct"
                  size="sm"
                  showSign
                />
              </div>
            ))}
          </div>
        </div>

        {/* Spread chart */}
        {hasSpreads && (
          <div className="card p-3">
            <ChartContainer option={buildLineOption(spreadChartSeries)} height="220px" />
            <div className="flex items-center gap-4 px-2 pt-2">
              {(latestSpread ?? []).map((item) => (
                <div key={item.label} className="flex items-center gap-1.5">
                  <span className="text-[0.65rem]" style={{ color: 'var(--text-faint)' }}>{item.label}</span>
                  <PercentileValue
                    value={item.value}
                    percentile={item.percentile}
                    format="pct"
                    size="sm"
                    showSign
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
