'use client';

import Link from 'next/link';
import { QUADRANT_CONFIG } from '@/lib/constants';
import type { Quadrant, RegimeTrailPoint } from '@/types';

interface Props {
  stateScore: number | null;
  stressScore: number | null;
  quadrant: string | null;
  trail: RegimeTrailPoint[];
}

export default function RegimeHero({ stateScore, stressScore, quadrant, trail }: Props) {
  const q = (quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  // Build mini sparkline SVG path from trail stress_score values
  const sparkPoints = trail.slice(-7);
  const svgWidth = 200;
  const svgHeight = 40;

  let sparkPath = '';
  if (sparkPoints.length > 1) {
    const minS = Math.min(...sparkPoints.map((p) => p.stress_score));
    const maxS = Math.max(...sparkPoints.map((p) => p.stress_score));
    const range = maxS - minS || 1;
    sparkPath = sparkPoints
      .map((p, i) => {
        const x = (i / (sparkPoints.length - 1)) * svgWidth;
        const y = svgHeight - ((p.stress_score - minS) / range) * (svgHeight - 8) - 4;
        return `${i === 0 ? 'M' : 'L'}${x},${y}`;
      })
      .join(' ');
  }

  return (
    <Link href="/regime" className="block animate-in stagger-1">
      <div className="card-dense" style={{ padding: 'var(--space-md) var(--space-lg)' }}>
        {/* Top row: label + scores */}
        <div className="flex items-center justify-between">
          <div
            className="text-[9px] uppercase tracking-wider"
            style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)', letterSpacing: '1px' }}
          >
            Current Regime
          </div>
          <div className="flex items-center gap-3">
            <div className="text-center">
              <div className="mono-value text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                {stateScore?.toFixed(0) ?? '--'}
              </div>
              <div className="text-[8px] uppercase" style={{ color: 'var(--text-faint)' }}>State</div>
            </div>
            <div style={{ width: 1, height: 24, background: 'var(--border-card)' }} />
            <div className="text-center">
              <div className="mono-value text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                {stressScore?.toFixed(0) ?? '--'}
              </div>
              <div className="text-[8px] uppercase" style={{ color: 'var(--text-faint)' }}>Stress</div>
            </div>
          </div>
        </div>

        {/* Regime name */}
        <div
          className="text-3xl font-bold mt-1"
          style={{ color: config.color }}
        >
          {config.label}
        </div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-faint)' }}>
          {q === 'Calm' && 'Low volatility, declining momentum'}
          {q === 'Transition' && 'Low volatility, rising momentum'}
          {q === 'Compression' && 'High volatility, declining momentum'}
          {q === 'Stress' && 'High volatility, rising momentum'}
        </div>

        {/* Mini sparkline */}
        {sparkPath && (
          <div
            className="mt-2 overflow-hidden"
            style={{ height: svgHeight, background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-sm)' }}
          >
            <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ width: '100%', height: '100%' }} preserveAspectRatio="none">
              <path d={sparkPath} fill="none" stroke={config.color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              {sparkPoints.length > 0 && (
                <circle
                  cx={svgWidth}
                  cy={(() => {
                    const last = sparkPoints[sparkPoints.length - 1];
                    const minS = Math.min(...sparkPoints.map((p) => p.stress_score));
                    const maxS = Math.max(...sparkPoints.map((p) => p.stress_score));
                    const range = maxS - minS || 1;
                    return svgHeight - ((last.stress_score - minS) / range) * (svgHeight - 8) - 4;
                  })()}
                  r="3"
                  fill={config.color}
                />
              )}
            </svg>
          </div>
        )}

        {/* Tap hint */}
        <div className="flex items-center justify-end mt-1">
          <span className="text-[9px]" style={{ color: 'var(--text-faint)' }}>Tap for detail</span>
          <span className="text-xs ml-1" style={{ color: 'var(--text-faint)' }}>&rsaquo;</span>
        </div>
      </div>
    </Link>
  );
}
