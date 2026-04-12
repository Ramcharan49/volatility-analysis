import type { Quadrant, TenorCode, DeltaBucket, MetricMeta, MetricFamily } from '@/types';

// Metric keys matching worker output
export const METRIC_KEYS = {
  ATM_IV_7D: 'atm_iv_7d',
  ATM_IV_30D: 'atm_iv_30d',
  ATM_IV_90D: 'atm_iv_90d',
  RR25_7D: 'rr25_7d',
  RR25_30D: 'rr25_30d',
  RR25_90D: 'rr25_90d',
  BF25_7D: 'bf25_7d',
  BF25_30D: 'bf25_30d',
  BF25_90D: 'bf25_90d',
  TERM_7D_30D: 'term_7d_30d',
  TERM_30D_90D: 'term_30d_90d',
  TERM_7D_90D: 'term_7d_90d',
  FRONT_END_DOMINANCE: 'front_end_dominance',
  STATE_SCORE: 'state_score',
  STRESS_SCORE: 'stress_score',
} as const;

// Flow metric base keys (append window code like _1d / _5m to form full metric_key).
export const FLOW_BASES = {
  D_ATM_IV_7D: 'd_atm_iv_7d',
  D_ATM_IV_30D: 'd_atm_iv_30d',
  D_RR25_30D: 'd_rr25_30d',
  D_BF25_30D: 'd_bf25_30d',
  D_FRONT_END_DOMINANCE: 'd_front_end_dominance',
} as const;

// Full 1-day flow metric keys as stored in metric_series_1m (window_code='1d').
export const FLOW_KEYS = {
  D_ATM_IV_7D_1D: 'd_atm_iv_7d_1d',
  D_ATM_IV_30D_1D: 'd_atm_iv_30d_1d',
  D_RR25_30D_1D: 'd_rr25_30d_1d',
  D_BF25_30D_1D: 'd_bf25_30d_1d',
  D_FRONT_END_DOMINANCE_1D: 'd_front_end_dominance_1d',
} as const;

// Percentile color scale — deep blue (low) → neutral → amber → red (extreme)
export const PERCENTILE_COLORS = [
  { min: 0, max: 10, color: '#3B82F6', label: 'Extremely low' },
  { min: 10, max: 20, color: '#60A5FA', label: 'Very low' },
  { min: 20, max: 40, color: '#6B7280', label: 'Below average' },
  { min: 40, max: 60, color: '#9CA3AF', label: 'Normal' },
  { min: 60, max: 80, color: '#F59E0B', label: 'Above average' },
  { min: 80, max: 90, color: '#EF4444', label: 'Very high' },
  { min: 90, max: 100, color: '#DC2626', label: 'Extremely elevated' },
] as const;

export function getPercentileColor(percentile: number | null | undefined): string {
  if (percentile == null) return '#595959'; // achromatic gray for missing
  const clamped = Math.max(0, Math.min(100, percentile));
  for (const band of PERCENTILE_COLORS) {
    if (clamped >= band.min && clamped < band.max) return band.color;
  }
  return '#DC2626'; // 100th percentile
}

export function getPercentileLabel(percentile: number | null | undefined): string {
  if (percentile == null) return '--';
  const clamped = Math.max(0, Math.min(100, percentile));
  for (const band of PERCENTILE_COLORS) {
    if (clamped >= band.min && clamped < band.max) return band.label;
  }
  return 'Extremely elevated';
}

// Quadrant styling
export const QUADRANT_CONFIG: Record<Quadrant, { color: string; bg: string; label: string }> = {
  Calm: { color: '#34D399', bg: 'rgba(52, 211, 153, 0.06)', label: 'Calm' },
  Transition: { color: '#FBBF24', bg: 'rgba(251, 191, 36, 0.06)', label: 'Transition' },
  Compression: { color: '#60A5FA', bg: 'rgba(96, 165, 250, 0.06)', label: 'Compression' },
  Stress: { color: '#F87171', bg: 'rgba(248, 113, 113, 0.06)', label: 'Stress' },
};

// Display labels
export const TENOR_LABELS: Record<TenorCode, string> = {
  '7d': '7D',
  '30d': '30D',
  '90d': '90D',
};

export const DELTA_LABELS: Record<DeltaBucket, string> = {
  P25: 'Put 25Δ',
  ATM: 'ATM',
  C25: 'Call 25Δ',
};

export const WINDOW_LABELS = {
  '5m': '5min',
  '15m': '15min',
  '60m': '1hr',
  '1d': '1D',
} as const;

export const TENORS: TenorCode[] = ['7d', '30d', '90d'];
export const DELTAS: DeltaBucket[] = ['P25', 'ATM', 'C25'];

// Market hours (IST)
export const MARKET_OPEN_HOUR = 9;
export const MARKET_OPEN_MINUTE = 15;
export const MARKET_CLOSE_HOUR = 15;
export const MARKET_CLOSE_MINUTE = 30;

// ECharts dark theme overrides
export const CHART_THEME = {
  backgroundColor: 'transparent',
  textStyle: { color: '#b9b9b9' },
  title: { textStyle: { color: '#ffffff' } },
  legend: { textStyle: { color: '#b9b9b9' } },
  tooltip: {
    backgroundColor: 'rgba(33, 33, 33, 0.95)',
    borderColor: '#353535',
    textStyle: { color: '#ffffff' },
  },
  axisLine: { lineStyle: { color: '#353535' } },
  splitLine: { lineStyle: { color: '#212121' } },
} as const;

// ── Metric Registry ─────────────────────────────────────

export const METRIC_REGISTRY: Record<string, MetricMeta> = {
  atm_iv_7d: {
    key: 'atm_iv_7d',
    displayName: 'ATM IV 7D',
    shortName: 'IV 7D',
    tenor: '7d',
    family: 'volatility',
    color: '#0052ef',
    format: 'pct',
    relatedKeys: ['atm_iv_30d', 'atm_iv_90d'],
    spreadKey: null,
    explainer: 'At-the-money implied volatility for the 7-day tenor, reflecting short-term expected move.',
  },
  atm_iv_30d: {
    key: 'atm_iv_30d',
    displayName: 'ATM IV 30D',
    shortName: 'IV 30D',
    tenor: '30d',
    family: 'volatility',
    color: '#0052ef',
    format: 'pct',
    relatedKeys: ['atm_iv_7d', 'atm_iv_90d'],
    spreadKey: null,
    explainer: 'At-the-money implied volatility for the 30-day tenor, the most-watched vol benchmark.',
  },
  atm_iv_90d: {
    key: 'atm_iv_90d',
    displayName: 'ATM IV 90D',
    shortName: 'IV 90D',
    tenor: '90d',
    family: 'volatility',
    color: '#0052ef',
    format: 'pct',
    relatedKeys: ['atm_iv_7d', 'atm_iv_30d'],
    spreadKey: null,
    explainer: 'At-the-money implied volatility for the 90-day tenor, capturing longer-term vol expectations.',
  },
  rr25_7d: {
    key: 'rr25_7d',
    displayName: '25Δ Risk Reversal 7D',
    shortName: 'RR 7D',
    tenor: '7d',
    family: 'skew',
    color: '#a78bfa',
    format: 'raw',
    relatedKeys: ['rr25_30d', 'rr25_90d'],
    spreadKey: null,
    explainer:
      '25-delta risk reversal at 7 days — measures put-call skew and directional fear. ' +
      'Displayed with inverted percentile so "higher" uniformly reads as "more downside skew / more stress."',
    stressDirection: -1,
  },
  rr25_30d: {
    key: 'rr25_30d',
    displayName: '25Δ Risk Reversal 30D',
    shortName: 'RR 30D',
    tenor: '30d',
    family: 'skew',
    color: '#a78bfa',
    format: 'raw',
    relatedKeys: ['rr25_7d', 'rr25_90d'],
    spreadKey: null,
    explainer:
      '25-delta risk reversal at 30 days — the standard skew measure for ' +
      'directional sentiment. Displayed with inverted percentile so "higher" ' +
      'uniformly reads as "more downside skew / more stress."',
    stressDirection: -1,
  },
  rr25_90d: {
    key: 'rr25_90d',
    displayName: '25Δ Risk Reversal 90D',
    shortName: 'RR 90D',
    tenor: '90d',
    family: 'skew',
    color: '#a78bfa',
    format: 'raw',
    relatedKeys: ['rr25_7d', 'rr25_30d'],
    spreadKey: null,
    explainer:
      '25-delta risk reversal at 90 days — longer-term skew reflecting structural hedging demand. ' +
      'Displayed with inverted percentile so "higher" uniformly reads as "more downside skew / more stress."',
    stressDirection: -1,
  },
  bf25_7d: {
    key: 'bf25_7d',
    displayName: '25Δ Butterfly 7D',
    shortName: 'BF 7D',
    tenor: '7d',
    family: 'tail',
    color: '#fbbf24',
    format: 'raw',
    relatedKeys: ['bf25_30d', 'bf25_90d'],
    spreadKey: null,
    explainer: '25-delta butterfly spread at 7 days — measures tail-risk premium for near-term wings.',
  },
  bf25_30d: {
    key: 'bf25_30d',
    displayName: '25Δ Butterfly 30D',
    shortName: 'BF 30D',
    tenor: '30d',
    family: 'tail',
    color: '#fbbf24',
    format: 'raw',
    relatedKeys: ['bf25_7d', 'bf25_90d'],
    spreadKey: null,
    explainer: '25-delta butterfly spread at 30 days — the standard tail-risk premium gauge.',
  },
  bf25_90d: {
    key: 'bf25_90d',
    displayName: '25Δ Butterfly 90D',
    shortName: 'BF 90D',
    tenor: '90d',
    family: 'tail',
    color: '#fbbf24',
    format: 'raw',
    relatedKeys: ['bf25_7d', 'bf25_30d'],
    spreadKey: null,
    explainer: '25-delta butterfly spread at 90 days — longer-term tail-risk pricing.',
  },
  term_7d_30d: {
    key: 'term_7d_30d',
    displayName: 'Term Spread 7D/30D',
    shortName: 'TS 7/30',
    tenor: null,
    family: 'term',
    color: '#0052ef',
    format: 'raw',
    relatedKeys: ['term_30d_90d', 'term_7d_90d'],
    spreadKey: null,
    explainer: 'Ratio of 7-day to 30-day ATM IV — captures short-term vol premium or discount.',
  },
  term_30d_90d: {
    key: 'term_30d_90d',
    displayName: 'Term Spread 30D/90D',
    shortName: 'TS 30/90',
    tenor: null,
    family: 'term',
    color: '#0052ef',
    format: 'raw',
    relatedKeys: ['term_7d_30d', 'term_7d_90d'],
    spreadKey: null,
    explainer: 'Ratio of 30-day to 90-day ATM IV — measures medium-term term structure slope.',
  },
  term_7d_90d: {
    key: 'term_7d_90d',
    displayName: 'Term Spread 7D/90D',
    shortName: 'TS 7/90',
    tenor: null,
    family: 'term',
    color: '#0052ef',
    format: 'raw',
    relatedKeys: ['term_7d_30d', 'term_30d_90d'],
    spreadKey: null,
    explainer: 'Ratio of 7-day to 90-day ATM IV — full term structure compression/expansion signal.',
  },
  front_end_dominance: {
    key: 'front_end_dominance',
    displayName: 'Front-End Dominance',
    shortName: 'FED',
    tenor: null,
    family: 'fed',
    color: '#34d399',
    format: 'raw',
    relatedKeys: [],
    spreadKey: null,
    explainer: 'Composite measure of how much short-dated vol dominates the term structure.',
  },
  d_atm_iv_30d_1d: {
    key: 'd_atm_iv_30d_1d',
    displayName: 'Chg in 30D ATM IV',
    shortName: 'Δ 30D IV',
    tenor: '30d',
    family: 'volatility',
    color: '#0052ef',
    format: 'pct',
    relatedKeys: [],
    spreadKey: null,
    explainer:
      'One-day change in 30D ATM implied volatility. Percentile compares ' +
      'today\u2019s signed change against the historical distribution of 1-day ' +
      'changes. Displayed on a diverging bar so direction and magnitude are ' +
      'both visible: right-of-centre = vol rising (stress building), ' +
      'left-of-centre = vol easing.',
    flowDisplay: 'diverging',
  },
  d_rr25_30d_1d: {
    key: 'd_rr25_30d_1d',
    displayName: 'Chg in 30D 25Δ RR',
    shortName: 'Δ 30D RR',
    tenor: '30d',
    family: 'skew',
    color: '#a78bfa',
    format: 'raw',
    relatedKeys: [],
    spreadKey: null,
    explainer:
      'One-day change in 30D 25-delta risk reversal. Stress-aligned so that ' +
      'right-of-centre = downside fear expanding (RR becoming more negative) ' +
      'and left-of-centre = fear receding. Matches the inversion convention ' +
      'used on the 30D RR level tile.',
    stressDirection: -1,
    flowDisplay: 'diverging',
  },
};

/** Look up metric metadata; returns a sensible fallback for unknown keys. */
export function getMetricMeta(key: string): MetricMeta {
  if (METRIC_REGISTRY[key]) return METRIC_REGISTRY[key];
  return {
    key,
    displayName: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    shortName: key,
    tenor: null,
    family: 'volatility',
    color: '#595959',
    format: 'raw',
    relatedKeys: [],
    spreadKey: null,
    explainer: '',
  };
}

/**
 * Translate a raw statistical percentile into the product's stress-oriented
 * display percentile for a given metric. Always prefer this over showing raw
 * percentile directly in the UI, so the stress convention stays uniform
 * ("higher = more stress") across every tile, callout, and badge.
 */
export function getDisplayPercentile(
  metricKey: string,
  rawPercentile: number | null | undefined,
): number | null {
  if (rawPercentile == null) return null;
  const meta = getMetricMeta(metricKey);
  if (meta.stressDirection === -1) {
    return 100 - rawPercentile;
  }
  return rawPercentile;
}

export const FAMILY_COLORS: Record<MetricFamily, string> = {
  volatility: '#0052ef',
  skew: '#a78bfa',
  tail: '#fbbf24',
  fed: '#34d399',
  term: '#0052ef',
  regime: '#f87171',
};

export const BOTTOM_TABS = [
  { href: '/', label: 'Home', icon: 'home' },
  { href: '/surface', label: 'Surface', icon: 'surface' },
  { href: '/flow', label: 'Flow', icon: 'flow' },
] as const;
