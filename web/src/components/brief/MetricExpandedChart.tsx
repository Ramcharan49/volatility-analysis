'use client';

import { useMemo } from 'react';
import ChartContainer from '@/components/shared/ChartContainer';
import type { EChartsCoreOption } from 'echarts/core';
import type { MetricFormat } from '@/types';

interface Props {
  timeSeries: { ts: string; value: number }[];
  color: string;
  format: MetricFormat;
}

function parseTs(ts: string): number {
  return new Date(ts.replace(' ', 'T').replace(/\+(\d{2})$/, '+$1:00')).getTime();
}

function formatValue(v: number, format: MetricFormat): string {
  switch (format) {
    case 'pct':
      return `${v.toFixed(2)}%`;
    case 'raw':
    default:
      return v.toFixed(2);
  }
}

export default function MetricExpandedChart({ timeSeries, color, format }: Props) {
  const option = useMemo<EChartsCoreOption>(() => {
    const data = timeSeries.map((d) => [parseTs(d.ts), d.value]);
    const lastPoint = data.length > 0 ? data[data.length - 1] : null;

    return {
      animation: true,
      animationDuration: 400,
      animationEasing: 'cubicOut',
      grid: { top: 6, right: 8, bottom: 20, left: 6, containLabel: false },
      xAxis: {
        type: 'time',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: 'var(--text-ghost)',
          fontSize: 8,
          fontFamily: 'var(--font-mono)',
          formatter: (value: number) => {
            const d = new Date(value);
            return `${d.getDate()}/${d.getMonth() + 1}`;
          },
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        show: false,
        scale: true,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(10, 10, 13, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.08)',
        borderWidth: 1,
        padding: [6, 10],
        textStyle: { color: '#f5f5f7', fontSize: 10, fontFamily: 'var(--font-mono)' },
        extraCssText:
          'backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); box-shadow: 0 8px 32px rgba(0,0,0,0.5);',
        axisPointer: { lineStyle: { color: 'rgba(255, 255, 255, 0.08)' } },
        formatter: (params: { value: [number, number] }[]) => {
          if (!params.length) return '';
          const [ts, val] = params[0].value;
          const d = new Date(ts);
          const dateStr = `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
          return `<strong>${dateStr}</strong><br/>${formatValue(val, format)}`;
        },
      },
      series: [
        {
          type: 'line',
          data,
          smooth: 0.35,
          symbol: 'none',
          lineStyle: {
            color,
            width: 1.6,
            shadowColor: color,
            shadowBlur: 10,
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: `${color}33` },
                { offset: 1, color: `${color}00` },
              ],
            },
          },
          emphasis: { disabled: true },
          z: 2,
        },
        ...(lastPoint
          ? [
              {
                type: 'scatter' as const,
                data: [lastPoint],
                symbol: 'circle',
                symbolSize: 5,
                itemStyle: {
                  color,
                  shadowColor: color,
                  shadowBlur: 12,
                },
                silent: true,
                z: 4,
              },
            ]
          : []),
      ],
    };
  }, [timeSeries, color, format]);

  if (!timeSeries || timeSeries.length === 0) {
    return <div className="flex-1" />;
  }

  return <ChartContainer option={option} height="100%" className="flex-1 min-h-0" />;
}
