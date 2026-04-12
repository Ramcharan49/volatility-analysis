'use client';

import { motion } from 'framer-motion';
import { QUADRANT_CONFIG } from '@/lib/constants';
import { formatStampDate } from '@/lib/formatting';
import type { Quadrant } from '@/types';

interface Props {
  insights: string[] | null;
  scenarios: string[] | null;
  quadrant: string | null;
  /** AI-generated paragraph from the worker; overrides the hardcoded join when present. */
  narrative?: string | null;
  /** ISO timestamp of the AI narrative. Only surfaces when `narrative` is present. */
  narrativeGeneratedAt?: string | null;
}

function joinAsProse(insights: string[], scenarios: string[]): string {
  const primary = insights.slice(0, 3).map((s) => s.trim().replace(/\.$/, '')).join('. ');
  const tail = scenarios.slice(0, 2).map((s) => s.trim().replace(/\.$/, '')).join('; ');
  if (primary && tail) return `${primary}. ${tail}.`;
  if (primary) return `${primary}.`;
  if (tail) return `${tail}.`;
  return '';
}

function AnalysisIcon({ color }: { color: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round">
      <circle cx="6" cy="6" r="4.5" />
      <path d="M6 3.5 L6 6 L7.7 7.3" />
    </svg>
  );
}

export default function RegimeAnalysis({
  insights,
  scenarios,
  quadrant,
  narrative,
  narrativeGeneratedAt,
}: Props) {
  const q = (quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  const aiNarrative = narrative?.trim() || null;
  const body = aiNarrative ?? joinAsProse(insights ?? [], scenarios ?? []);
  const hasBody = body.length > 0;
  const stamp = aiNarrative ? formatStampDate(narrativeGeneratedAt) : '';

  return (
    <motion.div
      className="glass-tile-static w-full px-5 py-4 relative overflow-hidden"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
    >
      <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--text-ghost)' }}>
        <AnalysisIcon color={config.color} />
        <span
          className="text-[10px] tracking-[0.22em] uppercase font-semibold"
          style={{ fontFamily: 'var(--font-label)' }}
        >
          Regime Analysis
        </span>
      </div>

      {hasBody ? (
        <p
          className="text-[13px]"
          style={{
            color: 'var(--text-hero)',
            fontFamily: 'var(--font-body)',
            lineHeight: 1.65,
            letterSpacing: '0.005em',
          }}
        >
          {body}
        </p>
      ) : (
        <p
          className="text-[12px]"
          style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-body)' }}
        >
          Awaiting signal. Regime commentary will populate once today&rsquo;s snapshot lands.
        </p>
      )}

      {aiNarrative && stamp && (
        <div
          className="mt-3 text-[9px] tracking-[0.22em] uppercase font-semibold"
          style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-label)' }}
        >
          AI generated · {stamp}
        </div>
      )}
    </motion.div>
  );
}
