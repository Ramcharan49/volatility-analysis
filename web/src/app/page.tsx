'use client';

import { useCallback, useMemo } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent, getRegimeTrail, getLatestFlowSnapshot } from '@/lib/queries';
import RegimeMap from '@/components/brief/RegimeMap';
import MetricGroup from '@/components/brief/MetricGroup';
import RegimeAnalysis from '@/components/brief/RegimeAnalysis';
import { HoverProvider } from '@/components/brief/HoverContext';
import type { DashboardCurrent, RegimeTrailPoint } from '@/types';

interface HomeData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
  flows: Record<string, { value: number | null; percentile: number | null }>;
}

const FLOW_KEYS_FOR_HOME = ['d_atm_iv_30d_1d', 'd_rr25_30d_1d'];

function LevelIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 8 L5 5 L7 7 L10 3" />
      <path d="M7 3 L10 3 L10 6" />
    </svg>
  );
}

function ShapeIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <path d="M6 1.5 L10.5 6 L6 10.5 L1.5 6 Z" />
      <path d="M6 3.5 L8.5 6 L6 8.5 L3.5 6 Z" />
    </svg>
  );
}

function MomentumIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 6 L3 6 L4.5 3 L6 9 L7.5 5 L9 7 L11 6" />
    </svg>
  );
}

export default function HomePage() {
  const fetchHome = useCallback(async (): Promise<HomeData | null> => {
    const [dashboard, trail, flows] = await Promise.all([
      getDashboardCurrent(),
      getRegimeTrail(7),
      getLatestFlowSnapshot(FLOW_KEYS_FOR_HOME),
    ]);
    return { dashboard, trail, flows };
  }, []);

  const { data, loading } = usePolling<HomeData>(fetchHome);

  const cardByKey = useMemo(() => {
    const map = new Map<string, { value: number | null; percentile: number | null }>();
    for (const card of data?.dashboard?.key_cards_json ?? []) {
      map.set(card.metric_key, {
        value: card.raw_value != null ? Number(card.raw_value) : null,
        percentile: card.percentile != null ? Number(card.percentile) : null,
      });
    }
    return map;
  }, [data]);

  if (loading && !data) {
    return (
      <div className="h-full w-full flex items-center justify-center">
        <span
          className="text-xs tracking-widest uppercase"
          style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-label)' }}
        >
          Loading signal…
        </span>
      </div>
    );
  }

  const db = data?.dashboard;
  const flows = data?.flows ?? {};

  const pct = (key: string) => cardByKey.get(key)?.percentile ?? null;
  const flowPct = (key: string) => flows[key]?.percentile ?? null;

  const levelRows = [
    { metricKey: 'atm_iv_7d', label: '7D ATM IV', percentile: pct('atm_iv_7d') },
    { metricKey: 'atm_iv_30d', label: '30D ATM IV', percentile: pct('atm_iv_30d') },
  ];
  const shapeRows = [
    { metricKey: 'term_7d_30d', label: '7D − 30D IV', percentile: pct('term_7d_30d') },
    { metricKey: 'rr25_30d', label: '30D 25Δ RR', percentile: pct('rr25_30d') },
  ];
  const momentumRows = [
    { metricKey: 'd_atm_iv_30d_1d', label: 'Chg 30D IV', percentile: flowPct('d_atm_iv_30d_1d') },
    { metricKey: 'd_rr25_30d_1d', label: 'Chg 30D RR', percentile: flowPct('d_rr25_30d_1d') },
  ];

  return (
    <HoverProvider>
      <div
        className="h-full w-full px-6 py-5 grid gap-5 min-h-0"
        style={{ gridTemplateColumns: '65fr 35fr', gridTemplateRows: 'minmax(0, 1fr) auto' }}
      >
        <div className="min-h-0 min-w-0">
          <RegimeMap
            stateScore={db?.state_score ?? null}
            stressScore={db?.stress_score ?? null}
            quadrant={db?.quadrant ?? null}
            trail={data?.trail ?? []}
          />
        </div>

        <div className="min-h-0 min-w-0 flex flex-col gap-3">
          <MetricGroup title="Volatility Level" icon={<LevelIcon />} rows={levelRows} />
          <MetricGroup title="Surface Shape" icon={<ShapeIcon />} rows={shapeRows} />
          <MetricGroup title="Surface Momentum" icon={<MomentumIcon />} rows={momentumRows} />
        </div>

        <div style={{ gridColumn: '1 / -1' }}>
          <RegimeAnalysis
            insights={db?.insight_bullets_json ?? null}
            scenarios={db?.scenario_implications_json ?? null}
            quadrant={db?.quadrant ?? null}
            narrative={db?.regime_narrative ?? null}
            narrativeGeneratedAt={db?.narrative_generated_at ?? null}
          />
        </div>
      </div>
    </HoverProvider>
  );
}
