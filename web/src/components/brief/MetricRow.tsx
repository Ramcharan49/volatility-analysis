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

// Shared constants across both bar variants.
const BAR_HEIGHT = 3;
const TRACK_BG = 'rgba(255, 255, 255, 0.05)';
const MIDLINE_COLOR = 'rgba(255, 255, 255, 0.14)';
const ANIM = { duration: 0.8, ease: [0.16, 1, 0.3, 1] as const };

/**
 * Left-anchored fill. Magnitude only — use for monotone percentile metrics
 * where "higher = more" is a meaningful, single-axis reading
 * (level metrics, term spreads, etc.).
 */
function LinearBar({
  percentile,
  color,
  label,
}: {
  percentile: number | null;
  color: string;
  label: string;
}) {
  const width = percentile != null ? Math.max(0, Math.min(100, percentile)) : 0;
  return (
    <div
      className="relative w-full rounded-full"
      style={{ height: BAR_HEIGHT, background: TRACK_BG }}
      role="meter"
      aria-label={label}
      aria-valuenow={percentile ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full"
        initial={{ width: 0 }}
        animate={{ width: `${width}%` }}
        transition={ANIM}
        style={{
          background: `linear-gradient(90deg, ${color} 0%, ${hexToRgba(color, 0.6)} 100%)`,
          boxShadow: `0 0 10px ${hexToRgba(color, 0.45)}`,
        }}
      />
    </div>
  );
}

/**
 * Centre-anchored fill for signed flow metrics. Percentile=50 is the neutral
 * midpoint ("today's change was at the historical median — i.e., typical /
 * no move"). Distance from centre = magnitude; side = direction.
 *
 * After stress-alignment (via `getDisplayPercentile` upstream), right-of-centre
 * uniformly means "stress building" and left-of-centre means "stress easing"
 * across every metric on the dashboard.
 *
 * The gradient deliberately brightens toward the tip of the fill (the data
 * point) and fades toward the centre (the anchor) — the eye lands on the
 * answer first, then traces back to see how far from neutral.
 */
function DivergingBar({
  percentile,
  color,
  label,
}: {
  percentile: number | null;
  color: string;
  label: string;
}) {
  const hasValue = percentile != null;
  const clamped = hasValue ? Math.max(0, Math.min(100, percentile as number)) : 50;
  const offsetFromCentre = clamped - 50;            // -50 … +50
  const halfWidth = Math.abs(offsetFromCentre);     // 0 … 50
  const leftPercent = offsetFromCentre < 0 ? 50 - halfWidth : 50;

  // Gradient brightens toward the TIP. For a left-extending fill the tip is
  // on the left; for a right-extending fill the tip is on the right.
  const gradient =
    offsetFromCentre < 0
      ? `linear-gradient(90deg, ${color} 0%, ${hexToRgba(color, 0.35)} 100%)`
      : `linear-gradient(90deg, ${hexToRgba(color, 0.35)} 0%, ${color} 100%)`;

  const ariaDirection =
    !hasValue || offsetFromCentre === 0
      ? 'neutral'
      : offsetFromCentre > 0
        ? 'rise'
        : 'drop';

  return (
    <div
      className="relative w-full rounded-full"
      style={{ height: BAR_HEIGHT, background: TRACK_BG }}
      role="meter"
      aria-label={`${label} (diverging; ${ariaDirection})`}
      aria-valuenow={percentile ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {/* Midline tick — 1px vertical line extending slightly above + below the
          track, signalling the neutral anchor point. */}
      <div
        className="absolute left-1/2"
        style={{
          top: -3,
          bottom: -3,
          width: 1,
          background: MIDLINE_COLOR,
          transform: 'translateX(-50%)',
          pointerEvents: 'none',
        }}
        aria-hidden="true"
      />
      {hasValue && (
        <motion.div
          className="absolute inset-y-0 rounded-full"
          initial={{ width: 0, left: '50%' }}
          animate={{ width: `${halfWidth}%`, left: `${leftPercent}%` }}
          transition={ANIM}
          style={{
            background: gradient,
            boxShadow: `0 0 10px ${hexToRgba(color, 0.45)}`,
          }}
        />
      )}
    </div>
  );
}

export default function MetricRow({ metricKey, label, percentile }: Props) {
  const { setHovered } = useHover();
  const meta = getMetricMeta(metricKey);
  const displayPct = getDisplayPercentile(metricKey, percentile);
  const color = getPercentileColor(displayPct);
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

  const barLabel = meta.displayName;

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

      {meta.flowDisplay === 'diverging' ? (
        <DivergingBar percentile={displayPct} color={color} label={barLabel} />
      ) : (
        <LinearBar percentile={displayPct} color={color} label={barLabel} />
      )}

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
