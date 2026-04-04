'use client';

import MetricCard from '@/components/shared/MetricCard';
import type { KeyCard } from '@/types';

interface Props {
  cards: KeyCard[] | null;
}

export default function KeyMetricCards({ cards }: Props) {
  if (!cards || cards.length === 0) return null;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {cards.map((card, i) => (
        <MetricCard
          key={card.metric_key}
          label={card.label}
          value={card.raw_value}
          percentile={card.percentile}
          format="pct"
          interpretation={card.interpretation}
          className={`animate-in stagger-${i + 3}`}
        />
      ))}
    </div>
  );
}
