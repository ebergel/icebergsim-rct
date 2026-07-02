import Plotly from "plotly.js-dist-min";
import { useEffect, useRef } from "react";

export interface PlotlyChartProps {
  data: unknown[];
  layout: Record<string, unknown>;
  testId?: string;
}

export function PlotlyChart({ data, layout, testId }: PlotlyChartProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    void Plotly.react(node, data, {
      autosize: true,
      margin: { t: 40, r: 20, b: 45, l: 55 },
      font: { family: "system-ui, sans-serif", size: 12 },
      ...layout,
    });
  }, [data, layout]);

  useEffect(() => {
    const node = ref.current;
    return () => {
      if (node) Plotly.purge(node);
    };
  }, []);

  return <div ref={ref} className="chart" data-testid={testId} />;
}
