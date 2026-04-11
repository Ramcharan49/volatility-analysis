'use client';

import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import ChartContainer from '@/components/shared/ChartContainer';

interface Props {
  data: number[];
  color: string;
  height?: number;
}

export default function Sparkline({ data, color, height = 44 }: Props) {
  const option = useMemo<EChartsCoreOption>(() => {
    const points = data.map((v, i) => [i, v]);
    const lastPoint = points.length > 0 ? points[points.length - 1] : null;
    return {
      animation: false,
      grid: { top: 6, right: 6, bottom: 4, left: 2, containLabel: false },
      xAxis: {
        type: 'value',
        show: false,
        min: 'dataMin',
        max: 'dataMax',
      },
      yAxis: {
        type: 'value',
        show: false,
        scale: true,
      },
      series: [
        {
          type: 'line',
          data: points,
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
          silent: true,
          z: 2,
        },
        // "Now" dot — anchors the line to the present moment
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
  }, [data, color]);

  if (!data || data.length === 0) {
    return <div style={{ height }} />;
  }

  return <ChartContainer option={option} height={`${height}px`} />;
}
