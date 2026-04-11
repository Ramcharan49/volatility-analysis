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
  regimeHovered: boolean;
  setHovered: (m: HoveredMetric | null) => void;
  setRegimeHovered: (b: boolean) => void;
}

const HoverContext = createContext<HoverContextValue | null>(null);

export function HoverProvider({ children }: { children: ReactNode }) {
  const [hovered, setHoveredState] = useState<HoveredMetric | null>(null);
  const [regimeHovered, setRegimeHoveredState] = useState(false);

  const setHovered = useCallback((m: HoveredMetric | null) => {
    setHoveredState(m);
  }, []);

  const setRegimeHovered = useCallback((b: boolean) => {
    setRegimeHoveredState(b);
  }, []);

  return (
    <HoverContext.Provider value={{ hovered, regimeHovered, setHovered, setRegimeHovered }}>
      {children}
    </HoverContext.Provider>
  );
}

export function useHover(): HoverContextValue {
  const ctx = useContext(HoverContext);
  if (!ctx) {
    // Silently return a no-op so components can be used standalone without provider
    return {
      hovered: null,
      regimeHovered: false,
      setHovered: () => {},
      setRegimeHovered: () => {},
    };
  }
  return ctx;
}
