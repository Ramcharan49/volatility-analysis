'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BOTTOM_TABS } from '@/lib/constants';
import MarketStatusBadge from './MarketStatusBadge';

function isTabActive(href: string, pathname: string): boolean {
  if (href === '/') return pathname === '/' || pathname === '/brief';
  return pathname.startsWith(href);
}

export default function TopNav() {
  const pathname = usePathname();

  return (
    <header className="top-nav">
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
          {BOTTOM_TABS.map((tab) => {
            const active = isTabActive(tab.href, pathname);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="relative px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all duration-150"
                style={{
                  fontFamily: 'var(--font-label)',
                  color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                  background: active ? 'var(--bg-surface)' : 'transparent',
                }}
              >
                {tab.label}
                {active && (
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
