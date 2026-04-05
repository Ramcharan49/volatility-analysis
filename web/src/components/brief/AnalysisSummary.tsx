'use client';

import { QUADRANT_CONFIG } from '@/lib/constants';
import type { Quadrant } from '@/types';

interface Props {
  quadrant: string | null;
  insights: string[] | null;
  scenarios: string[] | null;
}

export default function AnalysisSummary({ quadrant, insights, scenarios }: Props) {
  const allBullets = [...(insights ?? []), ...(scenarios ?? [])];
  if (allBullets.length === 0) return null;

  const q = (quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  return (
    <div className="card p-5 animate-in stagger-6">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-base" style={{ opacity: 0.7 }}>📊</span>
        <span
          className="text-xs font-semibold tracking-widest uppercase"
          style={{ fontFamily: 'var(--font-label)', color: 'var(--text-muted)' }}
        >
          Analysis Summary
        </span>
      </div>

      <div
        className="flex flex-col gap-3 pl-4"
        style={{ borderLeft: `2px solid ${config.color}40` }}
      >
        {allBullets.map((text, i) => (
          <p
            key={i}
            className="text-sm leading-relaxed"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--text-secondary)' }}
          >
            {text}
          </p>
        ))}
      </div>
    </div>
  );
}
