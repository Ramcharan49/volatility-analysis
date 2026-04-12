'use client';

import { motion, type Variants } from 'framer-motion';
import type { ReactNode } from 'react';
import MetricRow from './MetricRow';

interface Row {
  metricKey: string;
  label: string;
  percentile: number | null;
}

interface Props {
  title: string;
  icon: ReactNode;
  rows: Row[];
}

const panelVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] },
  },
};

export default function MetricGroup({ title, icon, rows }: Props) {
  return (
    <motion.div
      variants={panelVariants}
      initial="hidden"
      animate="show"
      className="glass-tile-static flex-1 min-h-0 px-4 py-3 flex flex-col"
    >
      <div
        className="flex items-center gap-1.5 mb-2"
        style={{ color: 'var(--text-ghost)' }}
      >
        <span className="flex items-center">{icon}</span>
        <span
          className="text-[10px] tracking-[0.22em] uppercase font-semibold"
          style={{ fontFamily: 'var(--font-label)' }}
        >
          {title}
        </span>
      </div>

      <div className="flex flex-col divide-y divide-white/[0.04]">
        {rows.map((r) => (
          <MetricRow
            key={r.metricKey}
            metricKey={r.metricKey}
            label={r.label}
            percentile={r.percentile}
          />
        ))}
      </div>
    </motion.div>
  );
}
