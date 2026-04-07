'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import MarketStatusBadge from './MarketStatusBadge';

const TABS = [
  { href: '/brief', label: 'Daily Brief' },
  { href: '/surface', label: 'Surface' },
  { href: '/flow', label: 'Flow' },
  { href: '/alerts', label: 'Alerts' },
] as const;

export default function TabBar() {
  const pathname = usePathname();

  return (
    <header
      className="sticky top-0 z-50 flex items-center justify-between px-6 py-3"
      style={{
        background: 'rgba(11, 11, 11, 0.85)',
        borderBottom: '1px solid var(--border-primary)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <div className="flex items-center gap-1">
        {/* App title */}
        <div className="flex items-center gap-2.5 mr-6">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--cta-coral)' }}
          />
          <span
            className="text-sm font-semibold tracking-wide"
            style={{ color: 'var(--text-primary)' }}
          >
            NIFTY VOL
          </span>
        </div>

        {/* Tabs */}
        <nav className="flex items-center gap-0.5">
          {TABS.map((tab) => {
            const isActive = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="relative px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all duration-150"
                style={{
                  fontFamily: 'var(--font-label)',
                  color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                  background: isActive ? 'var(--bg-surface)' : 'transparent',
                }}
              >
                {tab.label}
                {isActive && (
                  <span
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-0.5 rounded-full"
                    style={{ background: 'var(--accent-cyan)' }}
                  />
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      <MarketStatusBadge />
    </header>
  );
}
