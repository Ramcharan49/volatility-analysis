'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { QUADRANT_CONFIG } from '@/lib/constants';
import type { Quadrant } from '@/types';

interface Props {
  open: boolean;
  onClose: () => void;
  quadrant: string | null;
  children: ReactNode;
}

export default function SummaryDrawer({ open, onClose, quadrant, children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  // ESC to close + restore focus when opening/closing
  useEffect(() => {
    if (!open) return;

    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      // Focus trap: cycle within the panel
      if (e.key === 'Tab' && panelRef.current) {
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) {
          e.preventDefault();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
      lastFocusedRef.current?.focus?.();
    };
  }, [open, onClose]);

  const q = (quadrant as Quadrant) ?? 'Calm';
  const regimeConfig = QUADRANT_CONFIG[q] ?? QUADRANT_CONFIG.Calm;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Dim backdrop — click to close */}
          <motion.div
            className="fixed inset-0 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] as const }}
            style={{ background: 'rgba(5, 5, 7, 0.45)' }}
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Sliding glass panel */}
          <motion.div
            ref={panelRef}
            className="fixed right-0 top-0 bottom-0 z-50 flex flex-col outline-none"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 280, damping: 30, mass: 0.9 }}
            style={{
              width: 440,
              maxWidth: '90vw',
              background: 'rgba(10, 10, 13, 0.72)',
              backdropFilter: 'blur(24px) saturate(1.4)',
              WebkitBackdropFilter: 'blur(24px) saturate(1.4)',
              borderLeft: '1px solid var(--glass-border-hover)',
              boxShadow:
                '-24px 0 60px rgba(0, 0, 0, 0.6), -1px 0 0 rgba(255, 255, 255, 0.05) inset',
            }}
            role="dialog"
            aria-modal="true"
            aria-label="Insights summary"
            tabIndex={-1}
          >
            {/* Header */}
            <header className="flex items-center justify-between px-8 pt-8 pb-6">
              <div className="flex items-center gap-3">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: regimeConfig.color,
                    boxShadow: `0 0 12px ${regimeConfig.color}, 0 0 4px ${regimeConfig.color}`,
                  }}
                />
                <div className="flex flex-col">
                  <span
                    className="text-[9px] tracking-[0.24em] uppercase font-semibold"
                    style={{ fontFamily: 'var(--font-label)', color: 'var(--text-ghost)' }}
                  >
                    Insights
                  </span>
                  <span
                    className="text-hero text-[18px]"
                    style={{ fontWeight: 600, lineHeight: 1.1 }}
                  >
                    {regimeConfig.label}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="w-8 h-8 rounded-full flex items-center justify-center transition-colors"
                style={{
                  background: 'var(--glass-bg)',
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-secondary)',
                }}
                aria-label="Close summary"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                >
                  <path d="M2 2L10 10M10 2L2 10" />
                </svg>
              </button>
            </header>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto px-8 pb-8">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
