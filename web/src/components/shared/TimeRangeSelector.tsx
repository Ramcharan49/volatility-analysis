'use client';

import type { TimeRange } from '@/types';

const RANGES: TimeRange[] = ['1D', '5D', '1M', '3M'];

interface Props {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

export default function TimeRangeSelector({ value, onChange }: Props) {
  return (
    <div className="toggle-group">
      {RANGES.map((r) => (
        <button
          key={r}
          className={`toggle-btn ${value === r ? 'active' : ''}`}
          onClick={() => onChange(r)}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
