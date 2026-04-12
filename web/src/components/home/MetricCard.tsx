'use client';

import Link from 'next/link';
import { getPercentileColor, getPercentileLabel, getMetricMeta } from '@/lib/constants';
import { getChangeColor } from '@/lib/formatting';
import type { KeyCard } from '@/types';

interface Props {
  card: KeyCard;
  staggerIndex: number;
}

export default function MetricCard({ card, staggerIndex }: Props) {
  const meta = getMetricMeta(card.metric_key);
  const pctColor = getPercentileColor(card.percentile);
  const pctLabel = getPercentileLabel(card.percentile);
  const changeColor = getChangeColor(card.raw_value);

  return (
    <Link href={`/metric/${card.metric_key}`} className={`block animate-in stagger-${Math.min(staggerIndex + 2, 8)}`}>
      <div className="card-dense flex items-center gap-3" style={{ padding: '12px 14px' }}>
        {/* Left: label + value */}
        <div className="flex-1 min-w-0">
          <div
            className="text-[11px] truncate"
            style={{ color: 'var(--text-muted)' }}
          >
            {card.label}
          </div>
          <div
            className="mono-value font-semibold truncate"
            style={{ fontSize: 22, color: 'var(--text-primary)', lineHeight: 1.2 }}
          >
            {card.value}
          </div>
        </div>

        {/* Right: percentile + interpretation */}
        <div className="text-right flex-shrink-0">
          <div
            className="mono-value text-sm font-semibold"
            style={{ color: pctColor }}
          >
            P{Math.round(card.percentile)}
          </div>
          <div
            className="text-[9px]"
            style={{ color: 'var(--text-faint)' }}
          >
            {pctLabel}
          </div>
        </div>

        {/* Chevron */}
        <div style={{ color: 'var(--border-accent)', fontSize: 16 }}>&rsaquo;</div>
      </div>
    </Link>
  );
}
