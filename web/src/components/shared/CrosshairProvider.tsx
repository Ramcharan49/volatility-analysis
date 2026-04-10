'use client';
import { createContext, useState, useCallback, type ReactNode } from 'react';

interface CrosshairContextValue {
  hoveredTs: number | null;
  setHoveredTs: (ts: number | null) => void;
}

export const CrosshairContext = createContext<CrosshairContextValue>({
  hoveredTs: null,
  setHoveredTs: () => {},
});

export default function CrosshairProvider({ children }: { children: ReactNode }) {
  const [hoveredTs, setHoveredTsRaw] = useState<number | null>(null);
  const setHoveredTs = useCallback((ts: number | null) => setHoveredTsRaw(ts), []);

  return (
    <CrosshairContext value={{ hoveredTs, setHoveredTs }}>
      {children}
    </CrosshairContext>
  );
}
