'use client';

import MetricCard from '@/components/shared/MetricCard';
import PercentileValue from '@/components/shared/PercentileValue';
import SectionHeader from '@/components/shared/SectionHeader';
import { METRIC_KEYS } from '@/lib/constants';
import type { MetricRow } from '@/types';

interface Props {
  metrics: MetricRow[];
}

function findMetric(metrics: MetricRow[], key: string): MetricRow | undefined {
  return metrics.find((m) => m.metric_key === key);
}

export default function VolatilityLevel({ metrics }: Props) {
  const iv7 = findMetric(metrics, METRIC_KEYS.ATM_IV_7D);
  const iv30 = findMetric(metrics, METRIC_KEYS.ATM_IV_30D);
  const iv90 = findMetric(metrics, METRIC_KEYS.ATM_IV_90D);
  const t730 = findMetric(metrics, METRIC_KEYS.TERM_7D_30D);
  const t3090 = findMetric(metrics, METRIC_KEYS.TERM_30D_90D);
  const t790 = findMetric(metrics, METRIC_KEYS.TERM_7D_90D);

  return (
    <div className="animate-in stagger-2">
      <SectionHeader title="Volatility Level" subtitle="ATM implied vol across tenors" />
      <div className="grid grid-cols-3 gap-3 mb-3">
        <MetricCard label="ATM IV 7D" value={iv7?.value != null ? Number(iv7.value) : null} percentile={iv7?.percentile != null ? Number(iv7.percentile) : null} />
        <MetricCard label="ATM IV 30D" value={iv30?.value != null ? Number(iv30.value) : null} percentile={iv30?.percentile != null ? Number(iv30.percentile) : null} />
        <MetricCard label="ATM IV 90D" value={iv90?.value != null ? Number(iv90.value) : null} percentile={iv90?.percentile != null ? Number(iv90.percentile) : null} />
      </div>
      {/* Term spreads */}
      <div
        className="flex items-center gap-6 px-4 py-2.5 rounded-lg"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
      >
        <span className="text-xs uppercase tracking-wider font-semibold" style={{ color: 'var(--text-faint)' }}>
          Term Spreads
        </span>
        <SpreadItem label="7D-30D" row={t730} />
        <SpreadItem label="30D-90D" row={t3090} />
        <SpreadItem label="7D-90D" row={t790} />
      </div>
    </div>
  );
}

function SpreadItem({ label, row }: { label: string; row: MetricRow | undefined }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <PercentileValue
        value={row?.value != null ? Number(row.value) : null}
        percentile={row?.percentile != null ? Number(row.percentile) : null}
        format="pct"
        size="sm"
        showSign
      />
      {row?.percentile != null && (
        <span className="mono-value text-[0.65rem]" style={{ color: 'var(--text-faint)' }}>
          ({Math.round(Number(row.percentile))}th)
        </span>
      )}
    </div>
  );
}
