'use client';

import Link from 'next/link';
import { motion, type Variants } from 'framer-motion';
import Sparkline from './Sparkline';
import CountUpNumber from './CountUpNumber';
import { getPercentileColor } from '@/lib/constants';
import type { MetricFormat } from '@/types';

interface SecondaryReading {
  label: string;
  percentile: number | null;
}

interface Props {
  metricKey: string;
  label: string;
  value: number | null;
  format: MetricFormat;
  percentile: number | null;
  series: number[];
  secondary?: SecondaryReading;
}

// Inherits "hidden"/"show" from BentoGrid container for entrance choreography.
const itemVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as const },
  },
};

export default function MetricTile({
  metricKey,
  label,
  value,
  format,
  percentile,
  series,
  secondary,
}: Props) {
  const pctColor = getPercentileColor(percentile);
  const pctText = percentile != null ? `P${Math.round(percentile)}` : '--';
  const railPosition = percentile != null ? Math.max(0, Math.min(100, percentile)) : null;

  return (
    <motion.div
      variants={itemVariants}
      whileHover={{
        y: -3,
        scale: 1.012,
        transition: { type: 'spring', stiffness: 380, damping: 26 },
      }}
      className="min-h-0"
    >
      <Link
        href={`/metric/${metricKey}`}
        className="glass-tile group relative flex flex-col justify-between p-6 min-h-0 h-full"
        style={{ textDecoration: 'none' }}
      >
        {/* Category label */}
        <div className="flex items-center justify-between">
          <span
            className="text-[10px] font-semibold tracking-[0.2em] uppercase"
            style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
          >
            {label}
          </span>
          <span
            className="mono-value text-[11px] font-semibold tracking-[0.1em]"
            style={{ color: pctColor }}
          >
            {pctText}
          </span>
        </div>

        {/* Hero number — count-up on polling update */}
        <div className="flex items-baseline gap-2 mt-2">
          <CountUpNumber
            value={value}
            format={format}
            className="text-hero"
            style={{ fontSize: 'clamp(30px, 3.4vw, 48px)', fontWeight: 600 }}
          />
        </div>

        {/* Percentile rail — 2px track spanning tile width with notch at current position */}
        <div className="relative mt-3 h-[2px] w-full" aria-hidden="true">
          <div
            className="absolute inset-0 rounded-full"
            style={{ background: 'rgba(255, 255, 255, 0.05)' }}
          />
          {railPosition != null && (
            <div
              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full"
              style={{
                left: `${railPosition}%`,
                transform: 'translate(-50%, -50%)',
                background: pctColor,
                boxShadow: `0 0 6px ${pctColor}, 0 0 2px ${pctColor}`,
              }}
            />
          )}
        </div>

        {/* Sparkline — floats inside glass, not hugging bottom */}
        <div
          className="mt-3 flex-1 min-h-0"
          style={{ color: pctColor }}
        >
          <Sparkline data={series} color={pctColor} height={44} />
        </div>

        {/* Secondary reading (e.g. 7D · P84) */}
        {secondary && (
          <div className="flex items-center gap-1.5 mt-2">
            <span
              className="text-[9px] tracking-[0.2em] uppercase font-semibold"
              style={{
                fontFamily: 'var(--font-label)',
                color: 'var(--text-ghost)',
              }}
            >
              {secondary.label}
            </span>
            <span
              className="text-[10px]"
              style={{ color: 'var(--text-ghost)' }}
            >
              ·
            </span>
            <span
              className="mono-value text-[10px] font-semibold"
              style={{ color: getPercentileColor(secondary.percentile) }}
            >
              {secondary.percentile != null ? `P${Math.round(secondary.percentile)}` : '--'}
            </span>
          </div>
        )}
      </Link>
    </motion.div>
  );
}
