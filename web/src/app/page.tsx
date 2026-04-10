'use client';

import { useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent, getRegimeTrail } from '@/lib/queries';
import RegimeMap from '@/components/brief/RegimeMap';
import KeyMetricCards from '@/components/brief/KeyMetricCards';
import AnalysisSummary from '@/components/brief/AnalysisSummary';
import DataQualityBar from '@/components/brief/DataQualityBar';
import { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import type { DashboardCurrent, RegimeTrailPoint } from '@/types';

interface HomeData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
}

export default function HomePage() {
  const fetchHome = useCallback(async (): Promise<HomeData | null> => {
    const [dashboard, trail] = await Promise.all([
      getDashboardCurrent(),
      getRegimeTrail(7),
    ]);
    return { dashboard, trail };
  }, []);

  const { data, loading } = usePolling<HomeData>(fetchHome);

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
        <SkeletonChart height="380px" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <LoadingSkeleton count={1} />
          <LoadingSkeleton count={1} />
          <LoadingSkeleton count={1} />
        </div>
      </div>
    );
  }

  const db = data?.dashboard;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-8">
      {/* Regime Map — full width scatter plot with built-in range selector */}
      <RegimeMap
        stateScore={db?.state_score ?? null}
        stressScore={db?.stress_score ?? null}
        quadrant={db?.quadrant ?? null}
        trail={data?.trail ?? []}
      />

      {/* Key Metric Cards — 3-column grid with percentile bars */}
      <KeyMetricCards cards={db?.key_cards_json ?? null} />

      {/* Analysis Summary */}
      <AnalysisSummary
        quadrant={db?.quadrant ?? null}
        insights={db?.insight_bullets_json ?? null}
        scenarios={db?.scenario_implications_json ?? null}
      />

      {/* Data Quality */}
      <DataQualityBar quality={db?.data_quality_json ?? null} asOf={db?.as_of ?? null} />
    </div>
  );
}
