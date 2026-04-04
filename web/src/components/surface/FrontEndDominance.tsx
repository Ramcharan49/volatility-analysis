'use client';

import PercentileValue from '@/components/shared/PercentileValue';
import { getPercentileColor, METRIC_KEYS } from '@/lib/constants';
import type { MetricRow } from '@/types';

interface Props {
  metrics: MetricRow[];
}

export default function FrontEndDominance({ metrics }: Props) {
  const fed = metrics.find((m) => m.metric_key === METRIC_KEYS.FRONT_END_DOMINANCE);
  const value = fed?.value != null ? Number(fed.value) : null;
  const percentile = fed?.percentile != null ? Number(fed.percentile) : null;
  const color = getPercentileColor(percentile);

  return (
    <div className="animate-in stagger-5">
      <div
        className="card px-5 py-4 flex items-center justify-between"
        style={{ borderLeft: `3px solid ${color}` }}
      >
        <div className="flex flex-col gap-1">
          <span className="section-header text-[0.65rem]">Front-End Dominance</span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            IV(7D) - IV(30D) spread
          </span>
        </div>
        <div className="flex items-center gap-4">
          <PercentileValue value={value} percentile={percentile} format="pct" size="lg" showSign />
          {percentile != null && (
            <span
              className="mono-value text-sm px-2 py-1 rounded"
              style={{ color, background: `${color}15` }}
            >
              {Math.round(percentile)}th %ile
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
