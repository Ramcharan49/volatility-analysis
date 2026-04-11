'use client';

import Link from 'next/link';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import Sparkline from './Sparkline';
import MetricExpandedChart from './MetricExpandedChart';
import CountUpNumber from './CountUpNumber';
import { getPercentileColor, getMetricMeta } from '@/lib/constants';
import { formatMetricValue } from '@/lib/formatting';
import { useHover } from './HoverContext';
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
  expanded?: boolean;
  onToggle?: () => void;
  timeSeries?: { ts: string; value: number }[];
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
  expanded = false,
  onToggle,
  timeSeries,
}: Props) {
  const pctColor = getPercentileColor(percentile);
  const pctText = percentile != null ? `P${Math.round(percentile)}` : '--';
  const railPosition = percentile != null ? Math.max(0, Math.min(100, percentile)) : null;

  const { setHovered, regimeHovered } = useHover();
  const meta = getMetricMeta(metricKey);

  const handleHoverStart = () => {
    setHovered({
      key: metricKey,
      displayName: meta.displayName,
      valueText: formatMetricValue(value, format),
      percentile,
      color: pctColor,
    });
  };
  const handleHoverEnd = () => setHovered(null);

  // Determine which deep-dive pages this metric maps to
  const hasFlow = meta.family !== 'term';

  return (
    <motion.div
      variants={itemVariants}
      whileHover={
        expanded
          ? undefined
          : {
              y: -3,
              scale: 1.012,
              transition: { type: 'spring', stiffness: 380, damping: 26 },
            }
      }
      onHoverStart={handleHoverStart}
      onHoverEnd={handleHoverEnd}
      className="min-h-0"
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle?.();
          }
        }}
        className="glass-tile group relative flex flex-col justify-between p-5 min-h-0 h-full"
        data-regime-hovered={regimeHovered ? 'true' : undefined}
        data-expanded={expanded ? 'true' : undefined}
        style={{ cursor: 'pointer' }}
      >
        <AnimatePresence mode="wait" initial={false}>
          {expanded ? (
            <motion.div
              key="detailed"
              className="flex flex-col h-full min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {/* Compact header — single line */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[10px] font-semibold tracking-[0.2em] uppercase"
                    style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                  >
                    {label}
                  </span>
                  <span
                    className="text-hero text-[14px]"
                    style={{ fontWeight: 600 }}
                  >
                    {formatMetricValue(value, format)}
                  </span>
                </div>
                <span
                  className="mono-value text-[10px] font-semibold tracking-[0.1em]"
                  style={{ color: pctColor }}
                >
                  {pctText}
                </span>
              </div>

              {/* Interactive chart — fills remaining space */}
              <div
                className="flex-1 min-h-0"
                onClick={(e) => e.stopPropagation()}
              >
                <MetricExpandedChart
                  timeSeries={timeSeries ?? []}
                  color={pctColor}
                  format={format}
                />
              </div>

              {/* Navigation pills */}
              <div
                className="flex items-center justify-end gap-2 mt-2"
                onClick={(e) => e.stopPropagation()}
              >
                <Link
                  href="/surface"
                  className="text-[9px] font-semibold tracking-[0.15em] uppercase px-2.5 py-1 rounded-full transition-colors duration-150"
                  style={{
                    fontFamily: 'var(--font-label)',
                    color: 'var(--text-muted)',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  Surface
                </Link>
                {hasFlow && (
                  <Link
                    href="/flow"
                    className="text-[9px] font-semibold tracking-[0.15em] uppercase px-2.5 py-1 rounded-full transition-colors duration-150"
                    style={{
                      fontFamily: 'var(--font-label)',
                      color: 'var(--text-muted)',
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                    }}
                  >
                    Flow
                  </Link>
                )}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="compact"
              className="flex flex-col justify-between h-full"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
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

              {/* Hero number */}
              <div className="flex items-baseline gap-2 mt-2">
                <CountUpNumber
                  value={value}
                  format={format}
                  className="text-hero"
                  style={{ fontSize: 'clamp(30px, 3.4vw, 48px)', fontWeight: 600 }}
                />
              </div>

              {/* Percentile rail */}
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

              {/* Sparkline */}
              <div className="mt-3 flex-1 min-h-0" style={{ color: pctColor }}>
                <Sparkline data={series} color={pctColor} height={44} />
              </div>

              {/* Secondary reading */}
              {secondary && (
                <div className="flex items-center gap-1.5 mt-2">
                  <span
                    className="text-[9px] tracking-[0.2em] uppercase font-semibold"
                    style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                  >
                    {secondary.label}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--text-ghost)' }}>
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
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
