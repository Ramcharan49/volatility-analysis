'use client';

import type { DataQuality } from '@/types';

interface Props {
  quality: DataQuality | null;
  asOf: string | null;
}

export default function DataQualityBar({ quality, asOf }: Props) {
  const items: { label: string; value: string }[] = [];

  if (quality?.usable_option_row_count != null && quality?.nifty_row_count != null) {
    items.push({ label: 'Usable', value: `${quality.usable_option_row_count}/${quality.nifty_row_count}` });
  }
  if (quality?.selected_strike_count != null) {
    items.push({ label: 'Strikes', value: `${quality.selected_strike_count}` });
  }
  if (quality?.selected_expiries != null) {
    items.push({ label: 'Expiries', value: `${quality.selected_expiries.length}` });
  }
  if (asOf) {
    const d = new Date(asOf);
    const timeStr = d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });
    items.push({ label: 'Last update', value: `${timeStr} IST` });
  }

  if (items.length === 0) return null;

  return (
    <div
      className="flex items-center gap-5 px-4 py-2.5 rounded-lg animate-in stagger-8"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
    >
      <span className="text-[0.65rem] uppercase tracking-widest font-semibold" style={{ color: 'var(--text-faint)' }}>
        Data Quality
      </span>
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <span className="text-xs" style={{ color: 'var(--text-faint)' }}>{item.label}</span>
          <span className="mono-value text-xs" style={{ color: 'var(--text-secondary)' }}>{item.value}</span>
        </div>
      ))}
    </div>
  );
}
