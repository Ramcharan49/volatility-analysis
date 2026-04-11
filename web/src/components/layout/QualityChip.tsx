'use client';

import { useCallback } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { getDashboardCurrent } from '@/lib/queries';
import type { DashboardCurrent } from '@/types';

type Status = 'healthy' | 'degraded' | 'stale' | 'unknown';

function deriveStatus(db: DashboardCurrent | null): { status: Status; ratio: number | null } {
  if (!db) return { status: 'unknown', ratio: null };
  const q = db.data_quality_json;
  if (!q || q.usable_option_row_count == null || q.nifty_row_count == null || q.nifty_row_count === 0) {
    return { status: 'unknown', ratio: null };
  }
  const ratio = q.usable_option_row_count / q.nifty_row_count;
  if (ratio >= 0.8) return { status: 'healthy', ratio };
  if (ratio >= 0.5) return { status: 'degraded', ratio };
  return { status: 'stale', ratio };
}

const STATUS_CONFIG: Record<Status, { label: string; color: string }> = {
  healthy: { label: 'Healthy', color: 'var(--neon-green)' },
  degraded: { label: 'Degraded', color: 'var(--neon-amber)' },
  stale: { label: 'Stale', color: 'var(--neon-red)' },
  unknown: { label: '—', color: 'var(--text-ghost)' },
};

export default function QualityChip() {
  const fetchFn = useCallback(() => getDashboardCurrent(), []);
  const { data } = usePolling<DashboardCurrent>(fetchFn);

  const { status, ratio } = deriveStatus(data);
  const cfg = STATUS_CONFIG[status];

  const tooltipLines: string[] = [];
  if (data?.data_quality_json) {
    const q = data.data_quality_json;
    if (q.usable_option_row_count != null && q.nifty_row_count != null) {
      tooltipLines.push(`Usable rows: ${q.usable_option_row_count}/${q.nifty_row_count}`);
    }
    if (q.selected_strike_count != null) {
      tooltipLines.push(`Strikes: ${q.selected_strike_count}`);
    }
    if (q.selected_expiries != null) {
      tooltipLines.push(`Expiries: ${q.selected_expiries.length}`);
    }
    if (data.as_of) {
      const d = new Date(data.as_of);
      tooltipLines.push(
        `Last update: ${d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })} IST`,
      );
    }
  }

  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full"
      style={{
        background: 'var(--glass-bg)',
        border: '1px solid var(--glass-border)',
        fontFamily: 'var(--font-label)',
      }}
      title={tooltipLines.join('\n')}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{
          background: cfg.color,
          boxShadow: `0 0 6px ${cfg.color}`,
        }}
      />
      <span
        className="text-[10px] font-semibold tracking-wider uppercase"
        style={{ color: 'var(--text-secondary)' }}
      >
        {cfg.label}
      </span>
      {ratio != null && (
        <span
          className="mono-value text-[10px]"
          style={{ color: 'var(--text-ghost)' }}
        >
          {Math.round(ratio * 100)}%
        </span>
      )}
    </div>
  );
}
