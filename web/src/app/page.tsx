'use client';

import { useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent, getRegimeTrail } from '@/lib/queries';
import RegimeHero from '@/components/home/RegimeHero';
import MetricCard from '@/components/home/MetricCard';
import AnalysisSummary from '@/components/brief/AnalysisSummary';
import DataQualityBar from '@/components/brief/DataQualityBar';
import { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import type { DashboardCurrent, RegimeTrailPoint } from '@/types';

interface HomeData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
}

const CATEGORY_ORDER = ['Volatility Level', 'Surface Shape', 'Surface Momentum'];

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
      <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
        <SkeletonChart height="180px" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <LoadingSkeleton count={1} />
          <LoadingSkeleton count={1} />
          <LoadingSkeleton count={1} />
        </div>
      </div>
    );
  }

  const db = data?.dashboard;
  const cards = db?.key_cards_json ?? [];

  // Group cards by category in predefined order
  const grouped: { category: string; items: typeof cards }[] = [];
  const cardsByCategory = new Map<string, typeof cards>();
  for (const card of cards) {
    const cat = card.category || 'Other';
    const arr = cardsByCategory.get(cat) ?? [];
    arr.push(card);
    cardsByCategory.set(cat, arr);
  }
  for (const cat of CATEGORY_ORDER) {
    const items = cardsByCategory.get(cat);
    if (items) {
      grouped.push({ category: cat, items });
      cardsByCategory.delete(cat);
    }
  }
  for (const [cat, items] of cardsByCategory) {
    grouped.push({ category: cat, items });
  }

  let cardIndex = 0;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
      {/* 2-column desktop layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left column: Regime + Insights */}
        <div className="lg:col-span-3 flex flex-col gap-4">
          <RegimeHero
            stateScore={db?.state_score ?? null}
            stressScore={db?.stress_score ?? null}
            quadrant={db?.quadrant ?? null}
            trail={data?.trail ?? []}
          />

          <AnalysisSummary
            quadrant={db?.quadrant ?? null}
            insights={db?.insight_bullets_json ?? null}
            scenarios={db?.scenario_implications_json ?? null}
          />

          <DataQualityBar quality={db?.data_quality_json ?? null} asOf={db?.as_of ?? null} />
        </div>

        {/* Right column: Key Metrics */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          {grouped.map(({ category, items }) => (
            <div key={category}>
              <div
                className="text-[9px] uppercase tracking-wider px-1 mb-2"
                style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)', letterSpacing: '0.8px' }}
              >
                {category}
              </div>
              <div className="flex flex-col gap-2">
                {items.map((card) => {
                  cardIndex++;
                  return <MetricCard key={card.metric_key} card={card} staggerIndex={cardIndex} />;
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
