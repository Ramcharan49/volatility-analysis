'use client';

import { getPercentileColor } from '@/lib/constants';

interface Props {
  value: number | null | undefined;
  percentile?: number | null;
  format?: 'pct' | 'bps' | 'score' | 'raw';
  size?: 'sm' | 'md' | 'lg';
  showSign?: boolean;
}

function formatValue(value: number | null | undefined, format: string, showSign: boolean): string {
  if (value == null) return '-.--';
  switch (format) {
    case 'pct':
      return `${showSign && value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`;
    case 'bps':
      return `${showSign && value > 0 ? '+' : ''}${(value * 10000).toFixed(0)}bp`;
    case 'score':
      return value.toFixed(1);
    case 'raw':
    default:
      return `${showSign && value > 0 ? '+' : ''}${value.toFixed(2)}`;
  }
}

const sizeClasses = {
  sm: 'text-sm',
  md: 'text-lg',
  lg: 'text-2xl font-semibold',
};

export default function PercentileValue({
  value,
  percentile,
  format = 'pct',
  size = 'md',
  showSign = false,
}: Props) {
  const color = getPercentileColor(percentile);
  const displayValue = formatValue(value, format, showSign);

  return (
    <span
      className={`mono-value ${sizeClasses[size]} transition-colors duration-300`}
      style={{ color }}
    >
      {displayValue}
    </span>
  );
}
