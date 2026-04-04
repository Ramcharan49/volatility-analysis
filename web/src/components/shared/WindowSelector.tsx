'use client';

import type { WindowCode } from '@/types';
import { WINDOW_LABELS } from '@/lib/constants';

const WINDOWS: WindowCode[] = ['5m', '15m', '60m', '1d'];

interface Props {
  value: WindowCode;
  onChange: (window: WindowCode) => void;
}

export default function WindowSelector({ value, onChange }: Props) {
  return (
    <div className="toggle-group">
      {WINDOWS.map((w) => (
        <button
          key={w}
          className={`toggle-btn ${value === w ? 'active' : ''}`}
          onClick={() => onChange(w)}
        >
          {WINDOW_LABELS[w]}
        </button>
      ))}
    </div>
  );
}
