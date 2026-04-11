'use client';

import { useEffect, useRef } from 'react';
import { animate, useMotionValue } from 'framer-motion';
import { formatMetricValue } from '@/lib/formatting';
import type { MetricFormat } from '@/types';

interface Props {
  value: number | null;
  format: MetricFormat;
  className?: string;
  style?: React.CSSProperties;
}

// Tweens hero numbers from previous → new over 600ms cubic-out whenever
// polling delivers a fresh value. First render snaps to the initial value
// (no count-from-zero).
export default function CountUpNumber({ value, format, className, style }: Props) {
  const motion = useMotionValue<number>(value ?? 0);
  const ref = useRef<HTMLSpanElement>(null);
  const lastValueRef = useRef<number | null>(null);
  const isFirstRenderRef = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (value == null) {
      el.textContent = formatMetricValue(null, format);
      lastValueRef.current = null;
      return;
    }

    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false;
      motion.set(value);
      el.textContent = formatMetricValue(value, format);
      lastValueRef.current = value;
      return;
    }

    if (lastValueRef.current === value) return;

    const controls = animate(motion, value, {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = formatMetricValue(v, format);
      },
    });
    lastValueRef.current = value;
    return () => controls.stop();
  }, [value, format, motion]);

  return (
    <span ref={ref} className={className} style={style}>
      {formatMetricValue(value, format)}
    </span>
  );
}
