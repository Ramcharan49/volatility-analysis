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
      <div className="max-w-lg mx-auto px-4 py-4 flex flex-col gap-3">
        <SkeletonChart height="140px" />
        <LoadingSkeleton count={3} />
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
    <div className="max-w-lg mx-auto px-4 py-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: 'var(--cta-coral)' }} />
          <span className="text-sm font-semibold tracking-wide" style={{ color: 'var(--text-primary)' }}>
            NIFTY VOL
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-[5px] h-[5px] rounded-full glow-dot" style={{ color: 'var(--success)' }} />
          <span className="mono-value text-[10px]" style={{ color: 'var(--text-faint)' }}>
            {new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })} IST
          </span>
        </div>
      </div>

      {/* Regime Hero */}
      <RegimeHero
        stateScore={db?.state_score ?? null}
        stressScore={db?.stress_score ?? null}
        quadrant={db?.quadrant ?? null}
        trail={data?.trail ?? []}
      />

      {/* Key Metrics */}
      {grouped.map(({ category, items }) => (
        <div key={category}>
          <div
            className="text-[8px] uppercase tracking-wider px-1 mb-1.5"
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

      {/* Insights */}
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
