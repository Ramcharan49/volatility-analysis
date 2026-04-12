import { getSupabase } from './supabase';
import type {
  DashboardCurrent,
  SurfaceCell,
  MetricRow,
  DailyBrief,
  RegimeTrailPoint,
  TimeRange,
} from '@/types';

export async function getDashboardCurrent(): Promise<DashboardCurrent | null> {
  const { data, error } = await getSupabase()
    .from('dashboard_current')
    .select('*')
    .maybeSingle();
  if (error) {
    console.error('getDashboardCurrent error:', error);
    return null;
  }
  return data;
}

export async function getSurfaceCells(): Promise<SurfaceCell[]> {
  const { data, error } = await getSupabase()
    .from('surface_cells_current')
    .select('*');
  if (error) {
    console.error('getSurfaceCells error:', error);
    return [];
  }
  return data ?? [];
}

/** Normalize Postgres timestamp to ISO 8601 for reliable JS/ECharts parsing */
function normalizeTs(row: MetricRow): MetricRow {
  return { ...row, ts: row.ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00') };
}

export async function getLatestMetrics(keys: string[]): Promise<MetricRow[]> {
  // Get the most recent row for each metric key
  const { data, error } = await getSupabase()
    .from('metric_series_1m')
    .select('*')
    .in('metric_key', keys)
    .order('ts', { ascending: false })
    .limit(keys.length * 3); // Allow for multiple tenors per key

  if (error) {
    console.error('getLatestMetrics error:', error);
    return [];
  }

  // Deduplicate: keep only the most recent row per (metric_key, tenor_code)
  const seen = new Set<string>();
  const result: MetricRow[] = [];
  for (const row of data ?? []) {
    const key = `${row.metric_key}:${row.tenor_code ?? ''}`;
    if (!seen.has(key)) {
      seen.add(key);
      result.push(normalizeTs(row));
    }
  }
  return result;
}

function getTimeRangeFilter(range: TimeRange): string {
  const now = new Date();
  switch (range) {
    case '1D': {
      const d = new Date(now);
      d.setDate(d.getDate() - 1);
      return d.toISOString();
    }
    case '5D': {
      const d = new Date(now);
      d.setDate(d.getDate() - 5);
      return d.toISOString();
    }
    case '1M': {
      const d = new Date(now);
      d.setMonth(d.getMonth() - 1);
      return d.toISOString();
    }
    case '3M': {
      const d = new Date(now);
      d.setMonth(d.getMonth() - 3);
      return d.toISOString();
    }
  }
}

export async function getMetricSeries(
  keys: string[],
  range: TimeRange,
): Promise<MetricRow[]> {
  const since = getTimeRangeFilter(range);

  const { data, error } = await getSupabase()
    .from('metric_series_1m')
    .select('*')
    .in('metric_key', keys)
    .gte('ts', since)
    .order('ts', { ascending: true });

  if (error) {
    console.error('getMetricSeries error:', error);
    return [];
  }

  const rows = (data ?? []).map(normalizeTs);

  // Downsample for longer ranges
  if (range === '1M') {
    return downsampleHourly(rows);
  }
  if (range === '3M') {
    return downsampleDaily(rows);
  }
  return rows;
}

function downsampleHourly(rows: MetricRow[]): MetricRow[] {
  // Keep last row per (metric_key, hour)
  const buckets = new Map<string, MetricRow>();
  for (const row of rows) {
    const hour = row.ts.slice(0, 13); // "YYYY-MM-DDTHH"
    const key = `${row.metric_key}:${hour}`;
    buckets.set(key, row); // Last one wins (rows are sorted asc)
  }
  return Array.from(buckets.values()).sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  );
}

function downsampleDaily(rows: MetricRow[]): MetricRow[] {
  // Keep last row per (metric_key, day)
  const buckets = new Map<string, MetricRow>();
  for (const row of rows) {
    const day = row.ts.slice(0, 10); // "YYYY-MM-DD"
    const key = `${row.metric_key}:${day}`;
    buckets.set(key, row);
  }
  return Array.from(buckets.values()).sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  );
}

export async function getRegimeTrail(days: number): Promise<RegimeTrailPoint[]> {
  // Get state_score and stress_score for the last N trading days
  // Buffer extra days for weekends/holidays
  const buffer = days <= 10 ? 5 : Math.ceil(days * 0.5);
  const since = new Date();
  since.setDate(since.getDate() - (days + buffer));

  const { data, error } = await getSupabase()
    .from('metric_series_1m')
    .select('ts, metric_key, value')
    .in('metric_key', ['state_score', 'stress_score'])
    .gte('ts', since.toISOString())
    .order('ts', { ascending: true });

  if (error || !data) {
    console.error('getRegimeTrail error:', error);
    return [];
  }

  // Group by day, keep last value per (day, metric_key)
  const dayMap = new Map<string, { state: number; stress: number }>();
  for (const row of data) {
    const day = row.ts.slice(0, 10);
    if (!dayMap.has(day)) dayMap.set(day, { state: 0, stress: 0 });
    const entry = dayMap.get(day)!;
    if (row.metric_key === 'state_score' && row.value != null) {
      entry.state = Number(row.value);
    }
    if (row.metric_key === 'stress_score' && row.value != null) {
      entry.stress = Number(row.value);
    }
  }

  // Convert to array, take last N days
  return Array.from(dayMap.entries())
    .map(([date, scores]) => ({
      date,
      state_score: scores.state,
      stress_score: scores.stress,
    }))
    .slice(-days);
}

/** Latest 1-day window flow snapshot (value + percentile) per key. */
export async function getLatestFlowSnapshot(
  keys: string[],
): Promise<Record<string, { value: number | null; percentile: number | null }>> {
  const { data, error } = await getSupabase()
    .from('metric_series_1m')
    .select('metric_key, value, percentile, ts')
    .in('metric_key', keys)
    .eq('window_code', '1d')
    .order('ts', { ascending: false })
    .limit(keys.length * 4);

  const out: Record<string, { value: number | null; percentile: number | null }> = {};
  if (error) {
    console.error('getLatestFlowSnapshot error:', error);
    return out;
  }
  for (const row of data ?? []) {
    if (out[row.metric_key]) continue;
    out[row.metric_key] = {
      value: row.value != null ? Number(row.value) : null,
      percentile: row.percentile != null ? Number(row.percentile) : null,
    };
  }
  return out;
}

export async function getDailyBriefs(limit: number): Promise<DailyBrief[]> {
  const { data, error } = await getSupabase()
    .from('daily_brief_history')
    .select('*')
    .order('brief_date', { ascending: false })
    .limit(limit);

  if (error) {
    console.error('getDailyBriefs error:', error);
    return [];
  }
  return data ?? [];
}
