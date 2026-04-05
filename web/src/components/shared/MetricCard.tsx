'use client';

import PercentileValue from './PercentileValue';
import { getPercentileColor } from '@/lib/constants';

interface Props {
  label: string;
  value: number | null | undefined;
  percentile?: number | null;
  format?: 'pct' | 'bps' | 'score' | 'raw';
  interpretation?: string;
  showSign?: boolean;
  className?: string;
}

export default function MetricCard({
  label,
  value,
  percentile,
  format = 'pct',
  interpretation,
  showSign = false,
  className = '',
}: Props) {
  const pctColor = getPercentileColor(percentile);

  return (
    <div className={`card px-4 py-3.5 flex flex-col gap-2 ${className}`}>
      <span
        className="text-xs font-medium tracking-wide uppercase"
        style={{ fontFamily: 'var(--font-label)', color: 'var(--text-muted)' }}
      >
        {label}
      </span>
      <PercentileValue
        value={value}
        percentile={percentile}
        format={format}
        size="lg"
        showSign={showSign}
      />
      <div className="flex items-center gap-2">
        {percentile != null ? (
          <span
            className="text-xs font-medium px-1.5 py-0.5 rounded"
            style={{
              fontFamily: 'var(--font-label)',
              color: pctColor,
              background: `${pctColor}15`,
            }}
          >
            {Math.round(percentile)}th %ile
          </span>
        ) : (
          <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
            --
          </span>
        )}
        {interpretation && (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {interpretation}
          </span>
        )}
      </div>
    </div>
  );
}
