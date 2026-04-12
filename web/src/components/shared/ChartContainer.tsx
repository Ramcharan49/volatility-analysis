'use client';

import { useRef, useEffect } from 'react';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, ScatterChart, HeatmapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkAreaComponent,
  VisualMapComponent,
  DataZoomComponent,
  MarkPointComponent,
} from 'echarts/components';

echarts.use([
  CanvasRenderer,
  LineChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkAreaComponent,
  VisualMapComponent,
  DataZoomComponent,
  MarkPointComponent,
]);

interface Props {
  option: echarts.EChartsCoreOption;
  height?: string;
  className?: string;
  onInit?: (chart: echarts.ECharts) => void;
  /** Crosshair linking: emit hovered timestamp */
  onCrosshairMove?: (ts: number | null) => void;
  /** Crosshair linking: receive external timestamp to show tooltip */
  crosshairTs?: number | null;
}

export default function ChartContainer({
  option,
  height = '300px',
  className = '',
  onInit,
  onCrosshairMove,
  crosshairTs,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const crosshairRef = useRef(onCrosshairMove);

  // Keep the latest callback reachable without re-binding event handlers
  useEffect(() => {
    crosshairRef.current = onCrosshairMove;
  }, [onCrosshairMove]);

  // Init once on mount, dispose on unmount
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, undefined, {
      renderer: 'canvas',
    });
    chartRef.current = chart;
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: { color: '#b9b9b9', fontFamily: 'var(--font-display)' },
      ...option,
    });

    // Crosshair emission — uses ref so handlers never go stale
    chart.on('mousemove', (params) => {
      const cb = crosshairRef.current;
      if (!cb) return;
      const d = (params as unknown as { data?: unknown[] }).data;
      if (Array.isArray(d) && typeof d[0] === 'number') {
        cb(d[0]);
      }
    });
    chart.on('mouseout', () => crosshairRef.current?.(null));

    onInit?.(chart);

    return () => {
      chart.off('mousemove');
      chart.off('mouseout');
      chart.dispose();
      chartRef.current = null;
    };
    // Intentionally empty — init runs once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Merge-update when option changes (does NOT replay entrance animations)
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.setOption(
      { backgroundColor: 'transparent', textStyle: { color: '#b9b9b9', fontFamily: 'var(--font-display)' }, ...option },
      { notMerge: false, lazyUpdate: true },
    );
  }, [option]);

  // Crosshair reception: show tooltip at external timestamp
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || crosshairTs == null) return;
    chart.dispatchAction({
      type: 'showTip',
      seriesIndex: 0,
      dataIndex: undefined,
      x: undefined,
      position: undefined,
    });
    chart.dispatchAction({
      type: 'updateAxisPointer',
      currTrigger: 'mousemove',
      x: undefined,
      seriesIndex: 0,
      dataIndex: undefined,
    });
  }, [crosshairTs]);

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      chartRef.current?.resize({ animation: { duration: 200 } });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={`w-full ${className}`}
      style={{ height }}
    />
  );
}
