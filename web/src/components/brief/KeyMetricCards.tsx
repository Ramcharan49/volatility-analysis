'use client';

import { useMemo } from 'react';
import { getPercentileColor, getPercentileLabel } from '@/lib/constants';
import type { KeyCard } from '@/types';

interface Props {
  cards: KeyCard[] | null;
}

const CATEGORY_ICONS: Record<string, string> = {
  'Volatility Level': '〰',
  'Surface Shape': '◇',
  'Surface Momentum': '↗',
};

const CATEGORY_ORDER = ['Volatility Level', 'Surface Shape', 'Surface Momentum'];

function PercentileBar({ percentile }: { percentile: number }) {
  const color = getPercentileColor(percentile);
  const pct = Math.max(0, Math.min(100, percentile));

  return (
    <div
      className="w-full h-1.5 rounded-full overflow-hidden"
      style={{ background: 'var(--bg-primary)' }}
    >
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

export default function KeyMetricCards({ cards }: Props) {
  if (!cards || cards.length === 0) return null;

  const grouped = useMemo(() => {
    const map = new Map<string, KeyCard[]>();
    for (const card of cards) {
      const cat = card.category || 'Other';
      const arr = map.get(cat) ?? [];
      arr.push(card);
      map.set(cat, arr);
    }
    // Sort by predefined order, then any remaining
    const sorted: [string, KeyCard[]][] = [];
    for (const cat of CATEGORY_ORDER) {
      if (map.has(cat)) {
        sorted.push([cat, map.get(cat)!]);
        map.delete(cat);
      }
    }
    for (const [cat, items] of map) {
      sorted.push([cat, items]);
    }
    return sorted;
  }, [cards]);

  return (
    <div>
      <span
        className="text-xs font-semibold tracking-widest uppercase mb-4 block"
        style={{ fontFamily: 'var(--font-label)', color: 'var(--text-muted)' }}
      >
        Key Metrics
      </span>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {grouped.map(([category, items], gi) => {
          const accentColor = items[0] ? getPercentileColor(items[0].percentile) : 'var(--accent-cyan)';
          return (
            <div
              key={category}
              className={`card p-5 flex flex-col gap-4 animate-in stagger-${gi + 3}`}
              style={{ borderLeft: `3px solid ${accentColor}` }}
            >
              {/* Category header */}
              <div className="flex items-center gap-2">
                <span className="text-base" style={{ opacity: 0.7 }}>
                  {CATEGORY_ICONS[category] ?? '●'}
                </span>
                <span
                  className="text-xs font-bold tracking-widest uppercase"
                  style={{ fontFamily: 'var(--font-label)', color: 'var(--text-primary)' }}
                >
                  {category}
                </span>
              </div>

              {/* Metric rows */}
              {items.map((card) => {
                const pctColor = getPercentileColor(card.percentile);
                const pctLabel = getPercentileLabel(card.percentile);
                return (
                  <div key={card.metric_key} className="flex flex-col gap-1.5">
                    {/* Label + percentile value */}
                    <div className="flex items-center justify-between">
                      <span
                        className="text-sm"
                        style={{ fontFamily: 'var(--font-body)', color: 'var(--text-secondary)' }}
                      >
                        {card.label}
                      </span>
                      <span
                        className="text-sm font-bold"
                        style={{ fontFamily: 'var(--font-mono)', color: pctColor }}
                      >
                        {Math.round(card.percentile)}th
                      </span>
                    </div>
                    {/* Progress bar */}
                    <PercentileBar percentile={card.percentile} />
                    {/* Interpretation */}
                    <span
                      className="text-xs"
                      style={{ fontFamily: 'var(--font-label)', color: 'var(--text-faint)' }}
                    >
                      {pctLabel}
                    </span>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
