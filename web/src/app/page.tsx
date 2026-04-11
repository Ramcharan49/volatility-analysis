'use client';

import { useCallback, useMemo } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent, getRegimeTrail, getMetricSeries } from '@/lib/queries';
import { getMetricMeta } from '@/lib/constants';
import RegimeMap from '@/components/brief/RegimeMap';
import BentoGrid from '@/components/brief/BentoGrid';
import MetricTile from '@/components/brief/MetricTile';
import type { DashboardCurrent, RegimeTrailPoint, MetricRow } from '@/types';

interface HomeData {
  dashboard: DashboardCurrent | null;
  trail: RegimeTrailPoint[];
  series: MetricRow[];
}

// Hero metrics for the four bento tiles
const HERO_KEYS = ['atm_iv_30d', 'term_7d_30d', 'rr25_30d', 'bf25_30d'] as const;
const SECONDARY_KEYS = ['atm_iv_7d'] as const;
const ALL_KEYS = [...HERO_KEYS, ...SECONDARY_KEYS] as const;

export default function HomePage() {
  const fetchHome = useCallback(async (): Promise<HomeData | null> => {
    const [dashboard, trail, series] = await Promise.all([
      getDashboardCurrent(),
      getRegimeTrail(7),
      getMetricSeries([...ALL_KEYS], '1M'),
    ]);
    return { dashboard, trail, series };
  }, []);

  const { data, loading } = usePolling<HomeData>(fetchHome);

  const { seriesByKey, cardByKey } = useMemo(() => {
    const byKey = new Map<string, number[]>();
    for (const row of data?.series ?? []) {
      if (row.value == null) continue;
      const arr = byKey.get(row.metric_key) ?? [];
      arr.push(Number(row.value));
      byKey.set(row.metric_key, arr);
    }
    const cards = new Map<string, { value: number | null; percentile: number | null }>();
    for (const card of data?.dashboard?.key_cards_json ?? []) {
      cards.set(card.metric_key, {
        value: card.raw_value != null ? Number(card.raw_value) : null,
        percentile: card.percentile != null ? Number(card.percentile) : null,
      });
    }
    return { seriesByKey: byKey, cardByKey: cards };
  }, [data]);

  if (loading && !data) {
    return (
      <div className="h-full w-full flex items-center justify-center">
        <span className="text-xs tracking-widest uppercase" style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-label)' }}>
          Loading signal…
        </span>
      </div>
    );
  }

  const db = data?.dashboard;

  const tileFor = (key: string, label: string, secondary?: { key: string; label: string }) => {
    const meta = getMetricMeta(key);
    const card = cardByKey.get(key);
    const secondaryCard = secondary ? cardByKey.get(secondary.key) : undefined;
    return (
      <MetricTile
        key={key}
        metricKey={key}
        label={label}
        value={card?.value ?? null}
        format={meta.format}
        percentile={card?.percentile ?? null}
        series={seriesByKey.get(key) ?? []}
        secondary={
          secondary && secondaryCard
            ? { label: secondary.label, percentile: secondaryCard.percentile }
            : undefined
        }
      />
    );
  };

  return (
    <div className="h-full w-full px-6 py-5 grid gap-5 min-h-0" style={{ gridTemplateColumns: '65fr 35fr' }}>
      {/* Left: Regime Map (65%) */}
      <div className="min-h-0 min-w-0">
        <RegimeMap
          stateScore={db?.state_score ?? null}
          stressScore={db?.stress_score ?? null}
          quadrant={db?.quadrant ?? null}
          trail={data?.trail ?? []}
        />
      </div>

      {/* Right: Bento grid (35%) */}
      <div className="min-h-0 min-w-0 flex flex-col gap-3">
        <div className="flex-1 min-h-0">
          <BentoGrid>
            {tileFor('atm_iv_30d', 'Vol', { key: 'atm_iv_7d', label: '7D' })}
            {tileFor('term_7d_30d', 'Spread')}
            {tileFor('rr25_30d', 'Skew')}
            {tileFor('bf25_30d', 'Convexity')}
          </BentoGrid>
        </div>

        {/* Summary button placeholder — Phase 2 wires to slide-out panel */}
        <button
          type="button"
          className="self-end text-[10px] tracking-[0.18em] uppercase px-3 py-1.5 rounded-full transition-colors"
          style={{
            fontFamily: 'var(--font-label)',
            color: 'var(--text-secondary)',
            background: 'var(--glass-bg)',
            border: '1px solid var(--glass-border)',
          }}
          disabled
        >
          Summary ↗
        </button>
      </div>
    </div>
  );
}
