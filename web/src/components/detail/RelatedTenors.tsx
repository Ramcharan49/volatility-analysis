'use client';

import Link from 'next/link';
import { getMetricMeta } from '@/lib/constants';
import { formatMetricValue } from '@/lib/formatting';
import type { MetricRow } from '@/types';

interface Props {
  relatedKeys: string[];
  latestMap: Map<string, MetricRow>;
}

export default function RelatedTenors({ relatedKeys, latestMap }: Props) {
  if (relatedKeys.length === 0) return null;

  return (
    <div>
      <div
        className="text-[8px] uppercase tracking-wider px-1 mb-1"
        style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)', letterSpacing: '0.8px' }}
      >
        Other Tenors
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
        {relatedKeys.map((key) => {
          const meta = getMetricMeta(key);
          const row = latestMap.get(key);
          const value = row?.value != null ? Number(row.value) : null;
          const pct = row?.percentile != null ? Number(row.percentile) : null;

          return (
            <Link
              key={key}
              href={`/metric/${key}`}
              className="flex-shrink-0 card-dense"
              style={{ padding: '8px 12px', minWidth: 100 }}
            >
              <div className="text-[9px]" style={{ color: 'var(--text-faint)' }}>
                {meta.tenor?.toUpperCase() ?? meta.shortName}
              </div>
              <div className="flex items-baseline gap-1 mt-0.5">
                <span className="mono-value font-semibold" style={{ fontSize: 16, color: 'var(--text-primary)' }}>
                  {formatMetricValue(value, meta.format)}
                </span>
              </div>
              <div className="text-[8px] mt-0.5" style={{ color: 'var(--text-faint)' }}>
                {pct != null ? `P${Math.round(pct)}` : '--'}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
