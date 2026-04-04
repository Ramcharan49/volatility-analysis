'use client';

import { useState, useEffect } from 'react';
import {
  MARKET_OPEN_HOUR,
  MARKET_OPEN_MINUTE,
  MARKET_CLOSE_HOUR,
  MARKET_CLOSE_MINUTE,
} from '@/lib/constants';

function getISTTime(): Date {
  const now = new Date();
  const istOffset = 5.5 * 60 * 60 * 1000;
  return new Date(now.getTime() + istOffset + now.getTimezoneOffset() * 60 * 1000);
}

function checkMarketOpen(): boolean {
  const ist = getISTTime();
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;
  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const open = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE;
  const close = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE;
  return minutes >= open && minutes <= close;
}

function formatIST(date: Date): string {
  const ist = new Date(date.getTime() + 5.5 * 60 * 60 * 1000 + date.getTimezoneOffset() * 60 * 1000);
  const h = ist.getHours().toString().padStart(2, '0');
  const m = ist.getMinutes().toString().padStart(2, '0');
  return `${h}:${m} IST`;
}

export default function MarketStatusBadge() {
  const [isOpen, setIsOpen] = useState(false);
  const [time, setTime] = useState('');

  useEffect(() => {
    function update() {
      setIsOpen(checkMarketOpen());
      setTime(formatIST(new Date()));
    }
    update();
    const timer = setInterval(update, 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex items-center gap-2.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
      <div
        className="glow-dot"
        style={{
          background: isOpen ? '#34d399' : '#ef4444',
          color: isOpen ? '#34d399' : '#ef4444',
        }}
      />
      <span style={{ color: isOpen ? '#34d399' : 'var(--text-muted)' }}>
        {isOpen ? 'Live' : 'Closed'}
      </span>
      <span style={{ color: 'var(--text-faint)' }}>{time}</span>
    </div>
  );
}
