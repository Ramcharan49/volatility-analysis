'use client';

import Link from 'next/link';
import { useRegimeDetail } from '@/hooks/useRegimeDetail';
import RegimeMap from '@/components/brief/RegimeMap';
import { QUADRANT_CONFIG } from '@/lib/constants';
import { SkeletonChart } from '@/components/shared/LoadingSkeleton';
import type { Quadrant } from '@/types';

export default function RegimeDetailPage() {
  const { dashboard, trail, loading } = useRegimeDetail();

  if (loading && !dashboard) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-4">
        <SkeletonChart height="500px" />
      </div>
    );
  }

  const q = (dashboard?.quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  return (
    <div className="max-w-5xl mx-auto px-6 py-4 flex flex-col gap-4 page-enter">
      {/* Back nav */}
      <div className="flex items-center" style={{ padding: '4px 0' }}>
        <Link href="/" className="flex items-center gap-1.5">
          <span style={{ color: 'var(--accent-cyan)', fontSize: 14 }}>&lsaquo;</span>
          <span className="text-[11px]" style={{ color: 'var(--accent-cyan)' }}>Home</span>
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between px-1">
        <div>
          <div className="text-[9px] uppercase tracking-wider" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)' }}>
            Volatility Regime
          </div>
          <div className="text-2xl font-bold" style={{ color: config.color }}>
            {config.label}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-center">
            <div className="mono-value text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
              {dashboard?.state_score?.toFixed(0) ?? '--'}
            </div>
            <div className="text-[8px] uppercase" style={{ color: 'var(--text-faint)' }}>State</div>
          </div>
          <div style={{ width: 1, height: 28, background: 'var(--border-card)' }} />
          <div className="text-center">
            <div className="mono-value text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
              {dashboard?.stress_score?.toFixed(0) ?? '--'}
            </div>
            <div className="text-[8px] uppercase" style={{ color: 'var(--text-faint)' }}>Stress</div>
          </div>
        </div>
      </div>

      {/* Full regime map (reuses existing component) */}
      <RegimeMap
        stateScore={dashboard?.state_score ?? null}
        stressScore={dashboard?.stress_score ?? null}
        quadrant={dashboard?.quadrant ?? null}
        trail={trail}
      />
    </div>
  );
}
