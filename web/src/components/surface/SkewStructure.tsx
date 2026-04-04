'use client';

import MetricCard from '@/components/shared/MetricCard';
import PercentileValue from '@/components/shared/PercentileValue';
import SectionHeader from '@/components/shared/SectionHeader';
import { METRIC_KEYS } from '@/lib/constants';
import type { MetricRow } from '@/types';

interface Props {
  metrics: MetricRow[];
}

function find(metrics: MetricRow[], key: string) {
  return metrics.find((m) => m.metric_key === key);
}

export default function SkewStructure({ metrics }: Props) {
  const rr7 = find(metrics, METRIC_KEYS.RR25_7D);
  const rr30 = find(metrics, METRIC_KEYS.RR25_30D);
  const rr90 = find(metrics, METRIC_KEYS.RR25_90D);

  // Compute inter-tenor spreads client-side
  const rr730 = rr7?.value != null && rr30?.value != null ? Number(rr7.value) - Number(rr30.value) : null;
  const rr3090 = rr30?.value != null && rr90?.value != null ? Number(rr30.value) - Number(rr90.value) : null;
  const rr790 = rr7?.value != null && rr90?.value != null ? Number(rr7.value) - Number(rr90.value) : null;

  return (
    <div className="animate-in stagger-3">
      <SectionHeader title="Skew Structure" subtitle="25Δ risk reversal across tenors" />
      <div className="grid grid-cols-3 gap-3 mb-3">
        <MetricCard label="RR25 7D" value={rr7?.value != null ? Number(rr7.value) : null} percentile={rr7?.percentile != null ? Number(rr7.percentile) : null} showSign />
        <MetricCard label="RR25 30D" value={rr30?.value != null ? Number(rr30.value) : null} percentile={rr30?.percentile != null ? Number(rr30.percentile) : null} showSign />
        <MetricCard label="RR25 90D" value={rr90?.value != null ? Number(rr90.value) : null} percentile={rr90?.percentile != null ? Number(rr90.percentile) : null} showSign />
      </div>
      <div
        className="flex items-center gap-6 px-4 py-2.5 rounded-lg"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
      >
        <span className="text-xs uppercase tracking-wider font-semibold" style={{ color: 'var(--text-faint)' }}>
          RR Spreads
        </span>
        <SpreadVal label="7D-30D" value={rr730} />
        <SpreadVal label="30D-90D" value={rr3090} />
        <SpreadVal label="7D-90D" value={rr790} />
      </div>
    </div>
  );
}

function SpreadVal({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <PercentileValue value={value} format="pct" size="sm" showSign />
    </div>
  );
}
