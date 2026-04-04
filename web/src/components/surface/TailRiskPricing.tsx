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

export default function TailRiskPricing({ metrics }: Props) {
  const bf7 = find(metrics, METRIC_KEYS.BF25_7D);
  const bf30 = find(metrics, METRIC_KEYS.BF25_30D);
  const bf90 = find(metrics, METRIC_KEYS.BF25_90D);

  const bf730 = bf7?.value != null && bf30?.value != null ? Number(bf7.value) - Number(bf30.value) : null;
  const bf3090 = bf30?.value != null && bf90?.value != null ? Number(bf30.value) - Number(bf90.value) : null;
  const bf790 = bf7?.value != null && bf90?.value != null ? Number(bf7.value) - Number(bf90.value) : null;

  return (
    <div className="animate-in stagger-4">
      <SectionHeader title="Tail Risk Pricing" subtitle="25Δ butterfly across tenors" />
      <div className="grid grid-cols-3 gap-3 mb-3">
        <MetricCard label="BF25 7D" value={bf7?.value != null ? Number(bf7.value) : null} percentile={bf7?.percentile != null ? Number(bf7.percentile) : null} showSign />
        <MetricCard label="BF25 30D" value={bf30?.value != null ? Number(bf30.value) : null} percentile={bf30?.percentile != null ? Number(bf30.percentile) : null} showSign />
        <MetricCard label="BF25 90D" value={bf90?.value != null ? Number(bf90.value) : null} percentile={bf90?.percentile != null ? Number(bf90.percentile) : null} showSign />
      </div>
      <div
        className="flex items-center gap-6 px-4 py-2.5 rounded-lg"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
      >
        <span className="text-xs uppercase tracking-wider font-semibold" style={{ color: 'var(--text-faint)' }}>
          BF Spreads
        </span>
        <SpreadVal label="7D-30D" value={bf730} />
        <SpreadVal label="30D-90D" value={bf3090} />
        <SpreadVal label="7D-90D" value={bf790} />
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
