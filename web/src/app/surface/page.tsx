'use client';

import { useState, useCallback, useMemo } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getSurfaceCells, getMetricSeries, getLatestMetrics } from '@/lib/queries';
import { METRIC_KEYS } from '@/lib/constants';
import IVHeatmap from '@/components/surface/IVHeatmap';
import SurfaceMetricChart from '@/components/surface/SurfaceMetricChart';
import SectionHeader from '@/components/shared/SectionHeader';
import LoadingSkeleton, { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import type { SurfaceCell, MetricRow, TimeRange } from '@/types';

type SurfaceRange = '1W' | '1M' | '3M';

const RANGE_TO_TIME: Record<SurfaceRange, TimeRange> = {
  '1W': '5D',
  '1M': '1M',
  '3M': '3M',
};

const ALL_METRIC_KEYS = [
  METRIC_KEYS.ATM_IV_7D, METRIC_KEYS.ATM_IV_30D, METRIC_KEYS.ATM_IV_90D,
  METRIC_KEYS.RR25_7D, METRIC_KEYS.RR25_30D, METRIC_KEYS.RR25_90D,
  METRIC_KEYS.BF25_7D, METRIC_KEYS.BF25_30D, METRIC_KEYS.BF25_90D,
  METRIC_KEYS.TERM_7D_30D, METRIC_KEYS.TERM_30D_90D, METRIC_KEYS.TERM_7D_90D,
  METRIC_KEYS.FRONT_END_DOMINANCE,
];

// Spread pair definitions for client-side computation
const RR_SPREAD_PAIRS = [
  { label: '7d-30d', keyA: METRIC_KEYS.RR25_7D, keyB: METRIC_KEYS.RR25_30D },
  { label: '30d-90d', keyA: METRIC_KEYS.RR25_30D, keyB: METRIC_KEYS.RR25_90D },
  { label: '7d-90d', keyA: METRIC_KEYS.RR25_7D, keyB: METRIC_KEYS.RR25_90D },
];

const BF_SPREAD_PAIRS = [
  { label: '7d-30d', keyA: METRIC_KEYS.BF25_7D, keyB: METRIC_KEYS.BF25_30D },
  { label: '30d-90d', keyA: METRIC_KEYS.BF25_30D, keyB: METRIC_KEYS.BF25_90D },
  { label: '7d-90d', keyA: METRIC_KEYS.BF25_7D, keyB: METRIC_KEYS.BF25_90D },
];

interface SurfaceData {
  cells: SurfaceCell[];
  series: MetricRow[];
  latest: MetricRow[];
}

/** Compute spread series by aligning two metric series by date and subtracting */
function computeSpreadSeries(
  seriesMap: Map<string, MetricRow[]>,
  keyA: string,
  keyB: string,
): { ts: string; value: number }[] {
  const rowsA = seriesMap.get(keyA) ?? [];
  const rowsB = seriesMap.get(keyB) ?? [];

  // Index B by date for fast lookup
  const bByDate = new Map<string, number>();
  for (const row of rowsB) {
    if (row.value != null) {
      bByDate.set(row.ts.slice(0, 10), Number(row.value));
    }
  }

  const result: { ts: string; value: number }[] = [];
  for (const row of rowsA) {
    if (row.value == null) continue;
    const date = row.ts.slice(0, 10);
    const bVal = bByDate.get(date);
    if (bVal != null) {
      result.push({ ts: row.ts, value: Number(row.value) - bVal });
    }
  }
  return result;
}

export default function SurfacePage() {
  const [range, setRange] = useState<SurfaceRange>('1M');

  const fetchSurface = useCallback(async (): Promise<SurfaceData | null> => {
    const [cells, series, latest] = await Promise.all([
      getSurfaceCells(),
      getMetricSeries(ALL_METRIC_KEYS, RANGE_TO_TIME[range]),
      getLatestMetrics(ALL_METRIC_KEYS),
    ]);
    return { cells, series, latest };
  }, [range]);

  const { data, loading } = usePolling<SurfaceData>(fetchSurface);

  // Build maps for efficient lookups
  const seriesMap = useMemo(() => {
    const map = new Map<string, MetricRow[]>();
    for (const row of data?.series ?? []) {
      const arr = map.get(row.metric_key) ?? [];
      arr.push(row);
      map.set(row.metric_key, arr);
    }
    return map;
  }, [data?.series]);

  const latestMap = useMemo(() => {
    const map = new Map<string, MetricRow>();
    for (const row of data?.latest ?? []) {
      if (!map.has(row.metric_key)) {
        map.set(row.metric_key, row);
      }
    }
    return map;
  }, [data?.latest]);

  // Compute RR and BF spread series client-side
  const rrSpreadSeriesMap = useMemo(() => {
    const map = new Map<string, { ts: string; value: number }[]>();
    for (const pair of RR_SPREAD_PAIRS) {
      map.set(pair.label, computeSpreadSeries(seriesMap, pair.keyA, pair.keyB));
    }
    return map;
  }, [seriesMap]);

  const rrSpreadLatestMap = useMemo(() => {
    const map = new Map<string, { value: number }>();
    for (const pair of RR_SPREAD_PAIRS) {
      const a = latestMap.get(pair.keyA);
      const b = latestMap.get(pair.keyB);
      if (a?.value != null && b?.value != null) {
        map.set(pair.label, { value: Number(a.value) - Number(b.value) });
      }
    }
    return map;
  }, [latestMap]);

  const bfSpreadSeriesMap = useMemo(() => {
    const map = new Map<string, { ts: string; value: number }[]>();
    for (const pair of BF_SPREAD_PAIRS) {
      map.set(pair.label, computeSpreadSeries(seriesMap, pair.keyA, pair.keyB));
    }
    return map;
  }, [seriesMap]);

  const bfSpreadLatestMap = useMemo(() => {
    const map = new Map<string, { value: number }>();
    for (const pair of BF_SPREAD_PAIRS) {
      const a = latestMap.get(pair.keyA);
      const b = latestMap.get(pair.keyB);
      if (a?.value != null && b?.value != null) {
        map.set(pair.label, { value: Number(a.value) - Number(b.value) });
      }
    }
    return map;
  }, [latestMap]);

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
        <SkeletonChart height="220px" />
        <LoadingSkeleton count={3} />
        <LoadingSkeleton count={3} />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
      {/* Global controls bar */}
      <div
        className="flex items-center gap-4 px-4 py-3 rounded-lg sticky top-[52px] z-30"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)' }}
      >
        <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Range</span>
        <div className="toggle-group">
          {(['1W', '1M', '3M'] as SurfaceRange[]).map((r) => (
            <button
              key={r}
              className={`toggle-btn ${range === r ? 'active' : ''}`}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
        <span className="text-xs ml-2" style={{ color: 'var(--text-faint)' }}>
          Each point = 1 trading day
        </span>
      </div>

      {/* IV Heatmap */}
      <IVHeatmap cells={data?.cells ?? []} />

      {/* 1. Volatility Level */}
      <div className="animate-in stagger-2">
        <SectionHeader title="Volatility Level" subtitle="ATM implied vol across tenors" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <SurfaceMetricChart
            title="ATM Implied Volatility"
            options={[
              { label: '7D', key: METRIC_KEYS.ATM_IV_7D },
              { label: '30D', key: METRIC_KEYS.ATM_IV_30D },
              { label: '90D', key: METRIC_KEYS.ATM_IV_90D },
            ]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#0052ef"
          />
          <SurfaceMetricChart
            title="IV Term Spread"
            options={[
              { label: '7d-30d', key: METRIC_KEYS.TERM_7D_30D },
              { label: '30d-90d', key: METRIC_KEYS.TERM_30D_90D },
              { label: '7d-90d', key: METRIC_KEYS.TERM_7D_90D },
            ]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#0052ef"
            zeroline
            valueLabel="SPREAD"
          />
        </div>
      </div>

      {/* 2. Skew Structure */}
      <div className="animate-in stagger-3">
        <SectionHeader title="Skew Structure" subtitle="25Δ risk reversal across tenors" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <SurfaceMetricChart
            title="25Δ Risk Reversal"
            options={[
              { label: '7D', key: METRIC_KEYS.RR25_7D },
              { label: '30D', key: METRIC_KEYS.RR25_30D },
              { label: '90D', key: METRIC_KEYS.RR25_90D },
            ]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#a78bfa"
            zeroline
          />
          <SurfaceMetricChart
            title="RR Term Spread"
            options={[]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#a78bfa"
            zeroline
            valueLabel="SPREAD"
            spreadOptions={RR_SPREAD_PAIRS}
            spreadSeriesMap={rrSpreadSeriesMap}
            spreadLatestMap={rrSpreadLatestMap}
          />
        </div>
      </div>

      {/* 3. Tail Risk Pricing */}
      <div className="animate-in stagger-4">
        <SectionHeader title="Tail Risk Pricing" subtitle="25Δ butterfly across tenors" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <SurfaceMetricChart
            title="25Δ Butterfly"
            options={[
              { label: '7D', key: METRIC_KEYS.BF25_7D },
              { label: '30D', key: METRIC_KEYS.BF25_30D },
              { label: '90D', key: METRIC_KEYS.BF25_90D },
            ]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#fbbf24"
            zeroline
          />
          <SurfaceMetricChart
            title="BF Term Spread"
            options={[]}
            seriesMap={seriesMap}
            latestMap={latestMap}
            color="#fbbf24"
            zeroline
            valueLabel="SPREAD"
            spreadOptions={BF_SPREAD_PAIRS}
            spreadSeriesMap={bfSpreadSeriesMap}
            spreadLatestMap={bfSpreadLatestMap}
          />
        </div>
      </div>

      {/* 4. Front-End Dominance */}
      <div className="animate-in stagger-5">
        <SectionHeader title="Front-End Dominance" subtitle="IV(7D) - IV(30D) spread" />
        <SurfaceMetricChart
          title="FED Spread"
          options={[{ label: 'FED', key: METRIC_KEYS.FRONT_END_DOMINANCE }]}
          seriesMap={seriesMap}
          latestMap={latestMap}
          color="#34d399"
          zeroline
          valueLabel="VALUE"
        />
      </div>
    </div>
  );
}
