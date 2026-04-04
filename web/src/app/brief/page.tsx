'use client';

import { useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent, getRegimeTrail } from '@/lib/queries';
import RegimeMap from '@/components/brief/RegimeMap';
import RegimeInterpretation from '@/components/brief/RegimeInterpretation';
import KeyMetricCards from '@/components/brief/KeyMetricCards';
import DataQualityBar from '@/components/brief/DataQualityBar';
import LoadingSkeleton, { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import type { DashboardCurrent, RegimeTrailPoint } from '@/types';

interface BriefData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
}

export default function BriefPage() {
  const fetchBrief = useCallback(async (): Promise<BriefData | null> => {
    const [dashboard, trail] = await Promise.all([
      getDashboardCurrent(),
      getRegimeTrail(3),
    ]);
    return { dashboard, trail };
  }, []);

  const { data, loading } = usePolling<BriefData>(fetchBrief);

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <SkeletonChart height="340px" />
          <SkeletonChart height="340px" />
        </div>
        <LoadingSkeleton count={5} />
      </div>
    );
  }

  const db = data?.dashboard;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
      {/* Hero: Regime Map + Interpretation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RegimeMap
          stateScore={db?.state_score ?? null}
          stressScore={db?.stress_score ?? null}
          trail={data?.trail ?? []}
        />
        <RegimeInterpretation
          quadrant={db?.quadrant ?? null}
          stateScore={db?.state_score ?? null}
          stressScore={db?.stress_score ?? null}
          insights={db?.insight_bullets_json ?? null}
          scenarios={db?.scenario_implications_json ?? null}
        />
      </div>

      {/* Key Metric Cards */}
      <KeyMetricCards cards={db?.key_cards_json ?? null} />

      {/* Data Quality */}
      <DataQualityBar quality={db?.data_quality_json ?? null} asOf={db?.as_of ?? null} />
    </div>
  );
}
