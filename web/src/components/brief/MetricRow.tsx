'use client';

import { motion } from 'framer-motion';
import { getPercentileColor, getMetricMeta, getDisplayPercentile } from '@/lib/constants';
import { ordinalSuffix } from '@/lib/formatting';
import { useHover } from './HoverContext';

interface Props {
  metricKey: string;
  label: string;
  percentile: number | null;
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default function MetricRow({ metricKey, label, percentile }: Props) {
  const { setHovered } = useHover();
  const meta = getMetricMeta(metricKey);
  const displayPct = getDisplayPercentile(metricKey, percentile);
  const color = getPercentileColor(displayPct);
  const width = displayPct != null ? Math.max(0, Math.min(100, displayPct)) : 0;
  const pctInt = displayPct != null ? Math.round(displayPct) : null;
  const suffix = pctInt != null ? ordinalSuffix(pctInt) : '';

  const handleEnter = () => {
    setHovered({
      key: metricKey,
      displayName: meta.displayName,
      valueText: pctInt != null ? `P${pctInt}` : '--',
      percentile: displayPct,
      color,
    });
  };
  const handleLeave = () => setHovered(null);

  return (
    <motion.div
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      whileHover={{ y: -1 }}
      transition={{ type: 'spring', stiffness: 380, damping: 26 }}
      className="group grid items-center py-2"
      style={{ gridTemplateColumns: '40% 1fr auto', columnGap: 12 }}
    >
      <span
        className="text-[10px] tracking-[0.18em] uppercase font-semibold"
        style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
      >
        {label}
      </span>

      <div
        className="relative h-[3px] w-full rounded-full"
        style={{ background: 'rgba(255, 255, 255, 0.05)' }}
        aria-hidden="true"
      >
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${width}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          style={{
            background: `linear-gradient(90deg, ${color} 0%, ${hexToRgba(color, 0.6)} 100%)`,
            boxShadow: `0 0 10px ${hexToRgba(color, 0.45)}`,
          }}
        />
      </div>

      <div className="flex items-baseline justify-end tabular-nums">
        {pctInt != null ? (
          <>
            <span
              className="text-[22px] font-bold"
              style={{
                color: 'var(--text-hero)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '-0.01em',
              }}
            >
              {pctInt}
            </span>
            <span
              className="text-[11px] font-semibold ml-[2px]"
              style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-label)' }}
            >
              {suffix}
            </span>
          </>
        ) : (
          <span
            className="text-[16px] font-semibold"
            style={{ color: 'var(--text-ghost)', fontFamily: 'var(--font-mono)' }}
          >
            --
          </span>
        )}
      </div>
    </motion.div>
  );
}
