'use client';

import { useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getSurfaceCells, getLatestMetrics } from '@/lib/queries';
import { METRIC_KEYS } from '@/lib/constants';
import IVHeatmap from '@/components/surface/IVHeatmap';
import VolatilityLevel from '@/components/surface/VolatilityLevel';
import SkewStructure from '@/components/surface/SkewStructure';
import TailRiskPricing from '@/components/surface/TailRiskPricing';
import FrontEndDominance from '@/components/surface/FrontEndDominance';
import LoadingSkeleton, { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import type { SurfaceCell, MetricRow } from '@/types';

const SURFACE_METRIC_KEYS = [
  METRIC_KEYS.ATM_IV_7D, METRIC_KEYS.ATM_IV_30D, METRIC_KEYS.ATM_IV_90D,
  METRIC_KEYS.RR25_7D, METRIC_KEYS.RR25_30D, METRIC_KEYS.RR25_90D,
  METRIC_KEYS.BF25_7D, METRIC_KEYS.BF25_30D, METRIC_KEYS.BF25_90D,
  METRIC_KEYS.TERM_7D_30D, METRIC_KEYS.TERM_30D_90D, METRIC_KEYS.TERM_7D_90D,
  METRIC_KEYS.FRONT_END_DOMINANCE,
];

interface SurfaceData {
  cells: SurfaceCell[];
  metrics: MetricRow[];
}

export default function SurfacePage() {
  const fetchSurface = useCallback(async (): Promise<SurfaceData | null> => {
    const [cells, metrics] = await Promise.all([
      getSurfaceCells(),
      getLatestMetrics(SURFACE_METRIC_KEYS),
    ]);
    return { cells, metrics };
  }, []);

  const { data, loading } = usePolling<SurfaceData>(fetchSurface);

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
        <SkeletonChart height="220px" />
        <LoadingSkeleton count={3} />
        <LoadingSkeleton count={3} />
        <LoadingSkeleton count={3} />
      </div>
    );
  }

  const { cells, metrics } = data ?? { cells: [], metrics: [] };

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
      <IVHeatmap cells={cells} />
      <VolatilityLevel metrics={metrics} />
      <SkewStructure metrics={metrics} />
      <TailRiskPricing metrics={metrics} />
      <FrontEndDominance metrics={metrics} />
    </div>
  );
}
