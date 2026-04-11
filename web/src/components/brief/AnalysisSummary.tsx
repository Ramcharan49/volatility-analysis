'use client';

import { QUADRANT_CONFIG } from '@/lib/constants';
import type { Quadrant } from '@/types';

interface Props {
  quadrant: string | null;
  insights: string[] | null;
  scenarios: string[] | null;
}

// Content-only view — the enclosing drawer provides the glass material.
export default function AnalysisSummary({ quadrant, insights, scenarios }: Props) {
  const insightList = insights ?? [];
  const scenarioList = scenarios ?? [];
  const hasAny = insightList.length + scenarioList.length > 0;

  if (!hasAny) {
    return (
      <div
        className="text-[13px]"
        style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-body)' }}
      >
        No analysis available for this session.
      </div>
    );
  }

  const q = (quadrant as Quadrant) ?? 'Calm';
  const config = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  return (
    <div className="flex flex-col gap-8">
      {insightList.length > 0 && (
        <Section
          title="Insights"
          bullets={insightList}
          accent={config.color}
        />
      )}
      {scenarioList.length > 0 && (
        <Section
          title="Scenarios"
          bullets={scenarioList}
          accent={config.color}
        />
      )}
    </div>
  );
}

interface SectionProps {
  title: string;
  bullets: string[];
  accent: string;
}

function Section({ title, bullets, accent }: SectionProps) {
  return (
    <section>
      <h3
        className="text-[10px] font-semibold tracking-[0.22em] uppercase mb-4"
        style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
      >
        {title}
      </h3>
      <div
        className="flex flex-col gap-4 pl-5"
        style={{ borderLeft: `1px solid ${accent}66` }}
      >
        {bullets.map((text, i) => (
          <p
            key={i}
            className="text-[13px] leading-relaxed"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--text-secondary)' }}
          >
            {text}
          </p>
        ))}
      </div>
    </section>
  );
}
