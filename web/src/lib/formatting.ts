import type { MetricFormat } from '@/types';
import type { Quadrant } from '@/types';
import { QUADRANT_CONFIG, getPercentileColor, getPercentileLabel } from './constants';

/**
 * Format a metric value according to its format type.
 * Returns a display-ready string like "12.42%", "0.92", "-3.80".
 */
export function formatMetricValue(
  value: number | null | undefined,
  format: MetricFormat,
): string {
  if (value == null) return '--';
  switch (format) {
    case 'pct':
      return `${value.toFixed(2)}%`;
    case 'bps':
      return `${value.toFixed(0)} bps`;
    case 'score':
      return value.toFixed(1);
    case 'raw':
    default:
      return value.toFixed(2);
  }
}

/**
 * Format a change/delta value with explicit sign prefix.
 * Returns strings like "+3.57%", "-0.80", "+12 bps".
 */
export function formatChange(
  delta: number | null | undefined,
  format: MetricFormat,
): string {
  if (delta == null) return '--';
  const sign = delta > 0 ? '+' : '';
  switch (format) {
    case 'pct':
      return `${sign}${delta.toFixed(2)}%`;
    case 'bps':
      return `${sign}${delta.toFixed(0)} bps`;
    case 'score':
      return `${sign}${delta.toFixed(1)}`;
    case 'raw':
    default:
      return `${sign}${delta.toFixed(2)}`;
  }
}

/**
 * Return a color for a change value: green for positive, red for negative.
 */
export function getChangeColor(delta: number | null | undefined): string {
  if (delta == null) return '#595959';
  if (delta > 0) return '#34d399';
  if (delta < 0) return '#f87171';
  return '#595959';
}

/**
 * Return the color associated with a regime quadrant.
 */
export function getRegimeColor(quadrant: string | null | undefined): string {
  if (quadrant == null) return '#595959';
  const config = QUADRANT_CONFIG[quadrant as Quadrant];
  return config?.color ?? '#595959';
}

// Re-export percentile helpers from constants for centralized access
export { getPercentileColor, getPercentileLabel };
