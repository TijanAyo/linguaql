"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  chartType?: string;
  chartData?: any;
};

const INK = "#201e1d";
const ACCENT = "#ec3013";
const MUTED = "#605d5d";
const AXIS = "#d7d3d3";
const FONT = '"Archivo", system-ui, sans-serif';

export default function ChartRenderer({ chartType, chartData }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartType || chartType === "table" || !chartData) return;

    const chart = echarts.init(ref.current);
    let option: any = null;

    const axisCommon = {
      axisLine: { lineStyle: { color: AXIS } },
      axisTick: { show: false },
      axisLabel: { color: MUTED, fontFamily: FONT, fontSize: 11 },
      nameTextStyle: { color: MUTED, fontFamily: FONT, fontSize: 11 },
    };

    if (
      (chartType === "time_series" || chartType === "comparison") &&
      chartData.x &&
      chartData.y
    ) {
      option = {
        backgroundColor: "transparent",
        textStyle: { fontFamily: FONT, color: INK },
        grid: { left: 56, right: 24, top: 32, bottom: 40 },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#fff",
          borderColor: INK,
          borderWidth: 2,
          textStyle: { color: INK, fontFamily: FONT },
        },
        xAxis: {
          type: "category",
          data: chartData.x.map((v: any) => String(v)),
          name: chartData.x_label,
          ...axisCommon,
        },
        yAxis: {
          type: "value",
          name: chartData.y_label,
          splitLine: { lineStyle: { color: AXIS } },
          ...axisCommon,
        },
        series: [
          {
            data: chartData.y,
            type: chartType === "time_series" ? "line" : "bar",
            smooth: false,
            symbol: "circle",
            symbolSize: 6,
            itemStyle: { color: ACCENT },
            lineStyle: { color: ACCENT, width: 2 },
            areaStyle:
              chartType === "time_series"
                ? { color: ACCENT, opacity: 0.12 }
                : undefined,
          },
        ],
      };
    } else if (chartType === "stat" && chartData.value !== undefined) {
      option = {
        backgroundColor: "transparent",
        title: {
          text: String(chartData.value),
          subtext: chartData.label,
          left: "center",
          top: "center",
          textStyle: {
            fontSize: 48,
            color: ACCENT,
            fontFamily: FONT,
            fontWeight: 800,
          },
          subtextStyle: { fontSize: 14, color: MUTED, fontFamily: FONT },
        },
      };
    }

    if (option) chart.setOption(option);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [chartType, chartData]);

  if (!chartType || chartType === "table") return null;

  return <div ref={ref} className="chart" />;
}
