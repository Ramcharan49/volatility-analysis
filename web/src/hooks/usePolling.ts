'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE } from '@/lib/constants';

function isMarketOpen(): boolean {
  // Convert current UTC time to IST (UTC+5:30)
  const now = new Date();
  const istOffset = 5.5 * 60 * 60 * 1000;
  const ist = new Date(now.getTime() + istOffset + now.getTimezoneOffset() * 60 * 1000);

  const day = ist.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const open = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE;
  const close = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE;

  return minutes >= open && minutes <= close;
}

interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refetch: () => Promise<void>;
}

export function usePolling<T>(
  fetchFn: () => Promise<T | null>,
  intervalMs: number = 60_000,
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;

  const refetch = useCallback(async () => {
    try {
      setError(null);
      const result = await fetchRef.current();
      if (result !== null) {
        setData(result);
        setLastUpdated(new Date());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fetch failed');
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-fetch immediately whenever fetchFn identity changes (e.g. range/window switch)
  useEffect(() => {
    refetch();
  }, [fetchFn]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll on interval during market hours
  useEffect(() => {
    const timer = setInterval(() => {
      if (isMarketOpen() && navigator.onLine) {
        refetch();
      }
    }, intervalMs);

    return () => clearInterval(timer);
  }, [refetch, intervalMs]);

  return { data, loading, error, lastUpdated, refetch };
}
