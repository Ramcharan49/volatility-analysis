'use client';

import { use } from 'react';
import MetricDetailView from '@/components/detail/MetricDetailView';

export default function MetricPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  return <MetricDetailView metricKey={key} />;
}
