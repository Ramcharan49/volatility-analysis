'use client';

import { QUADRANT_CONFIG } from '@/lib/constants';
import type { Quadrant } from '@/types';

interface Props {
  quadrant: string | null;
  stateScore: number | null;
  stressScore: number | null;
  insights: string[] | null;
  scenarios: string[] | null;
}

export default function RegimeInterpretation({
  quadrant,
  stateScore,
  stressScore,
  insights,
  scenarios,
}: Props) {
  const q = (quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  return (
    <div className="card p-5 flex flex-col gap-4 animate-in stagger-2">
      {/* Regime badge */}
      <div className="flex items-center gap-3">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: config.color, boxShadow: `0 0 12px ${config.color}40` }}
        />
        <h2
          className="text-2xl font-bold tracking-tight"
          style={{ color: config.color }}
        >
          {config.label}
        </h2>
      </div>

      {/* Scores */}
      <div className="flex gap-5">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>
            State
          </span>
          <span className="mono-value text-lg" style={{ color: 'var(--text-primary)' }}>
            {stateScore != null ? stateScore.toFixed(1) : '--'}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>
            Stress
          </span>
          <span className="mono-value text-lg" style={{ color: 'var(--text-primary)' }}>
            {stressScore != null ? stressScore.toFixed(1) : '--'}
          </span>
        </div>
      </div>

      {/* Divider */}
      <div className="h-px w-full" style={{ background: 'var(--border-subtle)' }} />

      {/* Insight bullets */}
      {insights && insights.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="section-header text-[0.65rem]">Surface Signals</span>
          <ul className="flex flex-col gap-1.5">
            {insights.map((bullet, i) => (
              <li
                key={i}
                className="text-sm leading-relaxed pl-3 relative"
                style={{ color: 'var(--text-secondary)' }}
              >
                <span
                  className="absolute left-0 top-[9px] w-1 h-1 rounded-full"
                  style={{ background: config.color, opacity: 0.7 }}
                />
                {bullet}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Scenario implications */}
      {scenarios && scenarios.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="section-header text-[0.65rem]">Implications</span>
          <ul className="flex flex-col gap-1.5">
            {scenarios.map((s, i) => (
              <li
                key={i}
                className="text-sm leading-relaxed"
                style={{ color: 'var(--text-muted)' }}
              >
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
