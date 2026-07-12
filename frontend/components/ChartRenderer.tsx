"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  chartType?: string;
  chartData?: any;
};

export default function ChartRenderer({ chartType, chartData }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartType || chartType === "table" || !chartData) return;

    const chart = echarts.init(ref.current, "dark");
    let option: any = null;

    if (
      (chartType === "time_series" || chartType === "comparison") &&
      chartData.x &&
      chartData.y
    ) {
      option = {
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        xAxis: {
          type: "category",
          data: chartData.x.map((v: any) => String(v)),
          name: chartData.x_label,
        },
        yAxis: { type: "value", name: chartData.y_label },
        series: [
          {
            data: chartData.y,
            type: chartType === "time_series" ? "line" : "bar",
            smooth: chartType === "time_series",
            itemStyle: { color: "#4f9dff" },
            areaStyle: chartType === "time_series" ? { opacity: 0.15 } : undefined,
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
          textStyle: { fontSize: 42, color: "#e6e8eb" },
          subtextStyle: { fontSize: 14, color: "#9aa0aa" },
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

  return (
    <div
      ref={ref}
      style={{
        width: "100%",
        height: 360,
        marginTop: 16,
        background: "#1a1d24",
        border: "1px solid #2a2f3a",
        borderRadius: 8,
      }}
    />
  );
}
