'use client';

import { useState, useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getMetricSeries, getLatestMetrics } from '@/lib/queries';
import { FLOW_KEYS } from '@/lib/constants';
import FlowChartSection from '@/components/flow/FlowChartSection';
import WindowSelector from '@/components/shared/WindowSelector';
import TimeRangeSelector from '@/components/shared/TimeRangeSelector';
import LoadingSkeleton, { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import type { MetricRow, TimeRange, WindowCode, TenorCode } from '@/types';

interface FlowData {
  series: MetricRow[];
  latest: MetricRow[];
}

function filterByKey(rows: MetricRow[], fullKey: string): MetricRow[] {
  return rows.filter((r) => r.metric_key === fullKey);
}

function findLatest(rows: MetricRow[], fullKey: string): MetricRow | undefined {
  return rows.find((r) => r.metric_key === fullKey);
}

function latestVal(row: MetricRow | undefined): { value: number | null; percentile: number | null } {
  return {
    value: row?.value != null ? Number(row.value) : null,
    percentile: row?.percentile != null ? Number(row.percentile) : null,
  };
}

export default function FlowPage() {
  const [windowCode, setWindowCode] = useState<WindowCode>('1d');
  const [timeRange, setTimeRange] = useState<TimeRange>('1M');

  // Build metric keys matching what actually exists in DB:
  // d_atm_iv_7d_{window}, d_atm_iv_30d_{window}
  // d_rr25_30d_{window}, d_bf25_30d_{window}
  // d_front_end_dominance_{window}
  const w = windowCode;
  const allKeys = [
    `${FLOW_KEYS.D_ATM_IV_7D}_${w}`,
    `${FLOW_KEYS.D_ATM_IV_30D}_${w}`,
    `${FLOW_KEYS.D_RR25_30D}_${w}`,
    `${FLOW_KEYS.D_BF25_30D}_${w}`,
    `${FLOW_KEYS.D_FRONT_END_DOMINANCE}_${w}`,
  ];

  const fetchFlow = useCallback(async (): Promise<FlowData | null> => {
    const [series, latest] = await Promise.all([
      getMetricSeries(allKeys, timeRange),
      getLatestMetrics(allKeys),
    ]);
    return { series, latest };
  }, [windowCode, timeRange]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, loading } = usePolling<FlowData>(fetchFlow);

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
        <div className="flex gap-3"><div className="skeleton h-8 w-40" /><div className="skeleton h-8 w-40" /></div>
        <SkeletonChart height="250px" />
        <SkeletonChart height="250px" />
        <SkeletonChart height="250px" />
      </div>
    );
  }

  const series = data?.series ?? [];
  const latest = data?.latest ?? [];

  // Key helpers
  const atmIv7d = `${FLOW_KEYS.D_ATM_IV_7D}_${w}`;
  const atmIv30d = `${FLOW_KEYS.D_ATM_IV_30D}_${w}`;
  const rr25_30d = `${FLOW_KEYS.D_RR25_30D}_${w}`;
  const bf25_30d = `${FLOW_KEYS.D_BF25_30D}_${w}`;
  const fed = `${FLOW_KEYS.D_FRONT_END_DOMINANCE}_${w}`;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
      {/* Global controls */}
      <div
        className="flex items-center gap-4 px-4 py-3 rounded-lg sticky top-[52px] z-30"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)' }}
      >
        <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Window</span>
        <WindowSelector value={windowCode} onChange={setWindowCode} />
        <span className="text-xs font-medium ml-4" style={{ color: 'var(--text-muted)' }}>Range</span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
      </div>

      {/* 1. Volatility Momentum — ATM IV 7D and 30D */}
      <FlowChartSection
        title="Volatility Momentum"
        subtitle="ATM IV change across tenors"
        primarySeries={[
          { tenor: '7d', label: '7D', data: filterByKey(series, atmIv7d) },
          { tenor: '30d', label: '30D', data: filterByKey(series, atmIv30d) },
        ]}
        latestPrimary={[
          { label: 'Δ 7D', ...latestVal(findLatest(latest, atmIv7d)) },
          { label: 'Δ 30D', ...latestVal(findLatest(latest, atmIv30d)) },
        ]}
        staggerClass="stagger-1"
      />

      {/* 2. Skew Velocity — RR25 30D only */}
      <FlowChartSection
        title="Skew Velocity"
        subtitle="25Δ Risk Reversal 30D change"
        primarySeries={[
          { tenor: '30d', label: 'RR25 30D', data: filterByKey(series, rr25_30d) },
        ]}
        latestPrimary={[
          { label: 'Δ RR25 30D', ...latestVal(findLatest(latest, rr25_30d)) },
        ]}
        staggerClass="stagger-2"
      />

      {/* 3. Tail Risk Momentum — BF25 30D only */}
      <FlowChartSection
        title="Tail Risk Momentum"
        subtitle="25Δ Butterfly 30D change"
        primarySeries={[
          { tenor: '30d', label: 'BF25 30D', data: filterByKey(series, bf25_30d) },
        ]}
        latestPrimary={[
          { label: 'Δ BF25 30D', ...latestVal(findLatest(latest, bf25_30d)) },
        ]}
        staggerClass="stagger-3"
      />

      {/* 4. Front-End Dominance Flow */}
      <FlowChartSection
        title="Front-End Dominance Flow"
        subtitle="FED change over time"
        primarySeries={[
          { tenor: '7d', label: 'FED', data: filterByKey(series, fed) },
        ]}
        latestPrimary={[
          { label: 'Δ FED', ...latestVal(findLatest(latest, fed)) },
        ]}
        staggerClass="stagger-4"
      />
    </div>
  );
}
