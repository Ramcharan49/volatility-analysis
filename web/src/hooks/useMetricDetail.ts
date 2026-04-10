'use client';

import { useState, useCallback, useMemo } from 'react';
import { usePolling } from './usePolling';
import { getMetricSeries, getLatestMetrics } from '@/lib/queries';
import { getMetricMeta } from '@/lib/constants';
import type { MetricRow, TimeRange } from '@/types';

interface MetricDetailData {
  series: MetricRow[];
  latest: MetricRow[];
}

export function useMetricDetail(metricKey: string) {
  const [timeRange, setTimeRange] = useState<TimeRange>('1M');
  const meta = getMetricMeta(metricKey);
  const allKeys = [metricKey, ...meta.relatedKeys];

  const fetchFn = useCallback(async (): Promise<MetricDetailData | null> => {
    const [series, latest] = await Promise.all([
      getMetricSeries([metricKey], timeRange),
      getLatestMetrics(allKeys),
    ]);
    return { series, latest };
  }, [metricKey, timeRange]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, loading, error, lastUpdated } = usePolling<MetricDetailData>(fetchFn);

  const latestMap = useMemo(() => {
    const map = new Map<string, MetricRow>();
    for (const row of data?.latest ?? []) {
      if (!map.has(row.metric_key)) {
        map.set(row.metric_key, row);
      }
    }
    return map;
  }, [data?.latest]);

  const currentRow = latestMap.get(metricKey) ?? null;
  const series = data?.series?.filter((r) => r.metric_key === metricKey) ?? [];

  return {
    meta,
    series,
    currentRow,
    latestMap,
    loading,
    error,
    lastUpdated,
    timeRange,
    setTimeRange,
  };
}
