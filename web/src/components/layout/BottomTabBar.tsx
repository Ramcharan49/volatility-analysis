'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BOTTOM_TABS } from '@/lib/constants';

const icons: Record<string, (active: boolean) => React.ReactNode> = {
  home: (active) => (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M3 8.5L10 3L17 8.5V16C17 16.5523 16.5523 17 16 17H4C3.44772 17 3 16.5523 3 16V8.5Z"
        stroke={active ? 'var(--text-primary)' : '#595959'}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  surface: (active) => (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="3" width="5.5" height="5.5" rx="1" stroke={active ? 'var(--text-primary)' : '#595959'} strokeWidth="1.5" />
      <rect x="11.5" y="3" width="5.5" height="5.5" rx="1" stroke={active ? 'var(--text-primary)' : '#595959'} strokeWidth="1.5" />
      <rect x="3" y="11.5" width="5.5" height="5.5" rx="1" stroke={active ? 'var(--text-primary)' : '#595959'} strokeWidth="1.5" />
      <rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1" stroke={active ? 'var(--text-primary)' : '#595959'} strokeWidth="1.5" />
    </svg>
  ),
  flow: (active) => (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <polyline
        points="3,15 7,11 11,13 17,5"
        stroke={active ? 'var(--text-primary)' : '#595959'}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  ),
};

function isTabActive(href: string, pathname: string): boolean {
  if (href === '/') return pathname === '/' || pathname === '/brief';
  return pathname.startsWith(href);
}

export default function BottomTabBar() {
  const pathname = usePathname();

  return (
    <nav className="bottom-tab-bar">
      {BOTTOM_TABS.map((tab) => {
        const active = isTabActive(tab.href, pathname);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className="flex flex-col items-center gap-0.5"
          >
            {icons[tab.icon]?.(active)}
            <span
              className="text-[10px] font-medium"
              style={{
                fontFamily: 'var(--font-label)',
                color: active ? 'var(--text-primary)' : 'var(--text-faint)',
              }}
            >
              {tab.label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
