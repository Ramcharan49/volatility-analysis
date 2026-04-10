'use client';
import { getPercentileColor } from '@/lib/constants';

interface Props {
  percentile: number | null | undefined;
}

export default function PercentileBar({ percentile }: Props) {
  const pct = percentile != null ? Math.max(0, Math.min(100, percentile)) : 0;
  const color = getPercentileColor(percentile);

  return (
    <div className="w-full overflow-hidden" style={{ height: 3, background: 'var(--border-card)', borderRadius: 2 }}>
      <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}, ${color}cc)`, borderRadius: 2 }} />
    </div>
  );
}
