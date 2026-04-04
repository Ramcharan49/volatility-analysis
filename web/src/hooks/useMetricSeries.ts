'use client';

import { useState, useCallback } from 'react';
import { getMetricSeries } from '@/lib/queries';
import { usePolling } from './usePolling';
import type { MetricRow, TimeRange, WindowCode } from '@/types';

interface UseMetricSeriesResult {
  data: MetricRow[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  timeRange: TimeRange;
  setTimeRange: (r: TimeRange) => void;
  windowCode: WindowCode;
  setWindowCode: (w: WindowCode) => void;
}

export function useMetricSeries(
  baseKeys: string[],
  defaultRange: TimeRange = '1D',
  defaultWindow: WindowCode = '60m',
): UseMetricSeriesResult {
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);
  const [windowCode, setWindowCode] = useState<WindowCode>(defaultWindow);

  // Build full metric keys with window suffix
  const keys = baseKeys.map((k) => `${k}_${windowCode}`);

  const fetchFn = useCallback(
    () => getMetricSeries(keys, timeRange),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [keys.join(','), timeRange],
  );

  const { data, loading, error, lastUpdated } = usePolling<MetricRow[]>(fetchFn);

  return {
    data: data ?? [],
    loading,
    error,
    lastUpdated,
    timeRange,
    setTimeRange,
    windowCode,
    setWindowCode,
  };
}
