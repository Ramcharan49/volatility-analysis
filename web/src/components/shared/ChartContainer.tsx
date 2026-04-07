'use client';

import { useRef, useEffect, useCallback } from 'react';
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
]);

interface Props {
  option: echarts.EChartsCoreOption;
  height?: string;
  className?: string;
  onInit?: (chart: echarts.ECharts) => void;
}

export default function ChartContainer({ option, height = '300px', className = '', onInit }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const initChart = useCallback(() => {
    if (!containerRef.current) return;
    if (chartRef.current) {
      chartRef.current.dispose();
    }
    const chart = echarts.init(containerRef.current, undefined, {
      renderer: 'canvas',
    });
    chartRef.current = chart;
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: { color: '#b9b9b9', fontFamily: 'var(--font-display)' },
      ...option,
    });
    onInit?.(chart);
  }, [option, onInit]);

  useEffect(() => {
    initChart();
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [initChart]);

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
