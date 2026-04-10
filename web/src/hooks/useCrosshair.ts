'use client';
import { useContext } from 'react';
import { CrosshairContext } from '@/components/shared/CrosshairProvider';

export function useCrosshair() {
  return useContext(CrosshairContext);
}
