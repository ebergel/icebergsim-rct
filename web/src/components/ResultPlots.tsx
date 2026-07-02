import type { SimulationResponse } from "../types";
import { PlotlyChart } from "./PlotlyChart";

export function ResultPlots({ result }: { result: SimulationResponse }) {
  const scatter = result.plots.rr_vs_p;
  const histogram = result.plots.arr_histogram;

  // Plot data arrives ready-made from the server (SPEC §16); here we only draw.
  const points = scatter.x
    .map((x, i) => ({ x, y: scatter.y[i] }))
    .filter((p): p is { x: number; y: number } => p.x !== null && p.y !== null);

  const binCenters = histogram.counts.map(
    (_, i) => (histogram.bin_edges[i] + histogram.bin_edges[i + 1]) / 2,
  );
  const binWidth =
    histogram.bin_edges.length > 1 ? histogram.bin_edges[1] - histogram.bin_edges[0] : 1;

  return (
    <div className="plots">
      <PlotlyChart
        testId="rr-vs-p"
        data={[
          {
            type: "scattergl",
            mode: "markers",
            x: points.map((p) => p.x),
            y: points.map((p) => p.y),
            marker: { size: 4, opacity: 0.45, color: "#2563eb" },
            name: "simulated trials",
          },
        ]}
        layout={{
          title: { text: "Relative risk vs p-value — one point per simulated trial" },
          xaxis: { title: { text: "relative risk (RR)" } },
          yaxis: { title: { text: "p-value (log scale)" }, type: "log" },
          shapes: [
            {
              type: "line",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: scatter.alpha,
              y1: scatter.alpha,
              line: { color: "#dc2626", dash: "dash", width: 1.5 },
            },
          ],
          annotations: [
            {
              xref: "paper",
              x: 1,
              y: Math.log10(scatter.alpha),
              text: `α = ${scatter.alpha}`,
              showarrow: false,
              yanchor: "bottom",
              xanchor: "right",
              font: { color: "#dc2626" },
            },
          ],
          showlegend: false,
        }}
      />
      <PlotlyChart
        testId="arr-histogram"
        data={[
          {
            type: "bar",
            x: binCenters,
            y: histogram.counts,
            width: binWidth,
            marker: { color: "#0d9488" },
          },
        ]}
        layout={{
          title: {
            text: `ARR distribution across ${histogram.n_defined.toLocaleString()} replicates${
              histogram.n_undefined > 0 ? ` (${histogram.n_undefined} undefined excluded)` : ""
            }`,
          },
          xaxis: { title: { text: "absolute risk reduction (ARR)" } },
          yaxis: { title: { text: "simulated trials" } },
          bargap: 0.05,
          showlegend: false,
        }}
      />
    </div>
  );
}
