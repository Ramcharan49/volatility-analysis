'use client';

import { useCallback } from 'react';
import { usePolling } from './usePolling';
import { getDashboardCurrent, getRegimeTrail } from '@/lib/queries';
import type { DashboardCurrent, RegimeTrailPoint } from '@/types';

interface RegimeDetailData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
}

export function useRegimeDetail() {
  const fetchFn = useCallback(async (): Promise<RegimeDetailData | null> => {
    const [dashboard, trail] = await Promise.all([
      getDashboardCurrent(),
      getRegimeTrail(7),
    ]);
    return { dashboard, trail };
  }, []);

  const { data, loading, error } = usePolling<RegimeDetailData>(fetchFn);

  return {
    dashboard: data?.dashboard ?? null,
    trail: data?.trail ?? [],
    loading,
    error,
  };
}
