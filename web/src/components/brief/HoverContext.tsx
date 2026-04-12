'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export interface HoveredMetric {
  key: string;
  displayName: string;
  valueText: string;
  percentile: number | null;
  color: string;
}

interface HoverContextValue {
  hovered: HoveredMetric | null;
  setHovered: (m: HoveredMetric | null) => void;
}

const HoverContext = createContext<HoverContextValue | null>(null);

export function HoverProvider({ children }: { children: ReactNode }) {
  const [hovered, setHoveredState] = useState<HoveredMetric | null>(null);

  const setHovered = useCallback((m: HoveredMetric | null) => {
    setHoveredState(m);
  }, []);

  return (
    <HoverContext.Provider value={{ hovered, setHovered }}>
      {children}
    </HoverContext.Provider>
  );
}

export function useHover(): HoverContextValue {
  const ctx = useContext(HoverContext);
  if (!ctx) {
    return {
      hovered: null,
      setHovered: () => {},
    };
  }
  return ctx;
}
