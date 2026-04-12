// Types matching Supabase public schema

export interface DashboardCurrent {
  id: number;
  as_of: string | null;
  state_score: number | null;
  stress_score: number | null;
  quadrant: string | null;
  key_cards_json: KeyCard[] | null;
  insight_bullets_json: string[] | null;
  scenario_implications_json: string[] | null;
  data_quality_json: DataQuality | null;
  updated_at: string | null;
  regime_narrative: string | null;
  narrative_generated_at: string | null;
  narrative_model: string | null;
}

export interface KeyCard {
  label: string;
  value: string;
  raw_value: number;
  metric_key: string;
  percentile: number;
  interpretation: string;
  category: string;
  direction: string;
}

export interface DataQuality {
  raw_row_count?: number;
  nifty_row_count?: number;
  flow_anchor_date?: string;
  selected_expiries?: string[];
  selected_strike_count?: number;
  usable_option_row_count?: number;
}

export interface SurfaceCell {
  tenor_code: string;
  delta_bucket: string;
  as_of: string | null;
  iv: number | null;
  iv_percentile: number | null;
  quality_score: number | null;
}

export interface MetricRow {
  ts: string;
  metric_key: string;
  tenor_code: string | null;
  window_code: string | null;
  value: number | null;
  percentile: number | null;
  provisional: boolean | null;
  source_mode: string | null;
  created_at: string | null;
}

export interface DailyBrief {
  brief_date: string;
  generated_at: string | null;
  quadrant: string | null;
  state_score: number | null;
  stress_score: number | null;
  headline: string | null;
  body_text: string | null;
  key_metrics_json: Record<string, unknown> | null;
  data_quality_json: DataQuality | null;
  created_at: string | null;
}

export interface RegimeTrailPoint {
  date: string;
  state_score: number;
  stress_score: number;
}

export type Quadrant = 'Calm' | 'Transition' | 'Compression' | 'Stress';

export type TenorCode = '7d' | '30d' | '90d';
export type WindowCode = '5m' | '15m' | '60m' | '1d';
export type TimeRange = '1D' | '5D' | '1M' | '3M';
export type DeltaBucket = 'P25' | 'ATM' | 'C25';

export type MetricFormat = 'pct' | 'bps' | 'score' | 'raw';
export type MetricFamily = 'volatility' | 'skew' | 'tail' | 'fed' | 'term' | 'regime';

export interface MetricMeta {
  key: string;
  displayName: string;
  shortName: string;
  tenor: TenorCode | null;
  family: MetricFamily;
  color: string;
  format: MetricFormat;
  relatedKeys: string[];
  spreadKey: string | null;
  explainer: string;
  /**
   * Orientation of the percentile relative to the product's stress convention.
   *   +1 (default) — higher raw percentile = more stress (e.g., IV level).
   *   -1           — lower raw percentile = more stress (e.g., RR level).
   *                  Display is inverted to `100 - raw` so the UI reads uniformly:
   *                  "higher percentile = more stress" across the whole dashboard.
   * Mirrors worker/percentile.py _STRESS_DIRECTION_ALIGNS.
   */
  stressDirection?: 1 | -1;
}
