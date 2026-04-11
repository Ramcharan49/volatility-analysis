'use client';

import Link from 'next/link';
import Sparkline from './Sparkline';
import { formatMetricValue } from '@/lib/formatting';
import { getPercentileColor } from '@/lib/constants';
import type { MetricFormat } from '@/types';

interface SecondaryReading {
  label: string;
  percentile: number | null;
}

interface Props {
  metricKey: string;
  label: string;
  value: number | null;
  format: MetricFormat;
  percentile: number | null;
  series: number[];
  secondary?: SecondaryReading;
}

export default function MetricTile({
  metricKey,
  label,
  value,
  format,
  percentile,
  series,
  secondary,
}: Props) {
  const pctColor = getPercentileColor(percentile);
  const pctText = percentile != null ? `P${Math.round(percentile)}` : '--';
  const valueText = formatMetricValue(value, format);

  return (
    <Link
      href={`/metric/${metricKey}`}
      className="glass-tile group relative flex flex-col justify-between p-5 min-h-0"
      style={{ textDecoration: 'none' }}
    >
      {/* Category label */}
      <div className="flex items-center justify-between">
        <span
          className="text-ghost text-[10px] font-semibold"
          style={{ fontFamily: 'var(--font-label)' }}
        >
          {label}
        </span>
        <span
          className="mono-value text-xs font-semibold"
          style={{ color: pctColor }}
        >
          {pctText}
        </span>
      </div>

      {/* Hero number */}
      <div className="flex items-baseline gap-2 mt-1">
        <span
          className="text-hero"
          style={{ fontSize: 'clamp(28px, 3.2vw, 44px)', fontWeight: 600 }}
        >
          {valueText}
        </span>
      </div>

      {/* Sparkline */}
      <div
        className="mt-2"
        style={{ color: pctColor }}
      >
        <Sparkline data={series} color={pctColor} height={42} />
      </div>

      {/* Secondary reading (e.g. 7D · P84) */}
      {secondary && (
        <div className="flex items-center gap-1.5 mt-1">
          <span
            className="text-[10px]"
            style={{
              fontFamily: 'var(--font-label)',
              color: 'var(--text-ghost)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {secondary.label}
          </span>
          <span
            className="text-[10px]"
            style={{ color: 'var(--text-ghost)' }}
          >
            ·
          </span>
          <span
            className="mono-value text-[10px] font-semibold"
            style={{ color: getPercentileColor(secondary.percentile) }}
          >
            {secondary.percentile != null ? `P${Math.round(secondary.percentile)}` : '--'}
          </span>
        </div>
      )}
    </Link>
  );
}
