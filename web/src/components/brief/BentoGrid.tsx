'use client';

import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

export default function BentoGrid({ children }: Props) {
  return (
    <div className="grid grid-cols-2 grid-rows-2 gap-4 h-full min-h-0">
      {children}
    </div>
  );
}
