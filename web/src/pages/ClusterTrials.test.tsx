import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { ClusterResponse, ClusterSampleSizeResponse } from "../types";
import { ClusterTrials } from "./ClusterTrials";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    api: { ...original.api, clusterSampleSize: vi.fn(), cluster: vi.fn() },
  };
});

// Plotly needs a real WebGL canvas; in jsdom we only assert the chart is mounted.
vi.mock("../components/PlotlyChart", () => ({
  PlotlyChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const { api } = await import("../api");
const clusterSampleSize = vi.mocked(api.clusterSampleSize);
const cluster = vi.mocked(api.cluster);

// Canonical design-effect example: mean cluster size 100, ICC 0.01 ->
// DE = 1 + 99 * 0.01 = 1.99; adjusted n per arm 196.221 * 1.99 = 390.48; 4 clusters/arm.
const SIZE_RESPONSE: ClusterSampleSizeResponse = {
  individual_n_per_arm_unrounded: 196.221,
  design_effect: 1.99,
  cluster_adjusted_n_per_arm_unrounded: 390.48,
  n_per_arm_cluster_adjusted: 391,
  clusters_per_arm: 4,
  formula: "design_effect_1_plus_m_minus_1_icc (SPEC §14.2)",
};

// Simulated design where ignoring clustering looks better than it should:
// unadjusted power > adjusted power (anti-conservative, AXIOMS §11).
const CLUSTER_RESPONSE: ClusterResponse = {
  manifest: {
    input_hash: "d".repeat(64),
    random_seed: 12345,
    n_simulations: 5000,
    rng_algorithm: "PCG64",
    spec_version: "2.0.0-alpha.1",
  },
  design: {
    control_clusters: 4,
    intervention_clusters: 4,
    mean_cluster_size: 100,
    icc: 0.01,
    size_distribution: { type: "fixed", sd: null, min: 1, max: null },
  },
  summary: {
    mean_cer: 0.2,
    mean_eer: 0.1,
    mean_design_effect: 1.973,
    mean_cluster_level_difference: 0.099,
    power_unadjusted_chi_square: 0.62,
    power_adjusted_chi_square: 0.41,
    power_cluster_level_difference: 0.38,
  },
  notes: [
    "unadjusted_chi_square analyzes cluster-correlated individuals as independent and is anti-conservative (AXIOMS §11)",
    "adjusted_chi_square divides the Pearson statistic by the design effect 1 + (m - 1) * ICC using the realized mean cluster size (SPEC §14.4)",
    "cluster_level_difference uses a pooled two-sample t-test on cluster event proportions with df = k_control + k_intervention - 2 (SPEC §14.4)",
  ],
};

beforeEach(() => {
  clusterSampleSize.mockReset();
  cluster.mockReset();
});

describe("ClusterTrials", () => {
  it("runs both requests and renders size cards, analysis table, chart, notes, manifest", async () => {
    clusterSampleSize.mockResolvedValue(SIZE_RESPONSE);
    cluster.mockResolvedValue(CLUSTER_RESPONSE);
    render(<ClusterTrials />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();

    // Both requests submitted concurrently with the form defaults.
    expect(clusterSampleSize).toHaveBeenCalledTimes(1);
    expect(clusterSampleSize).toHaveBeenCalledWith({
      p_control: 0.2,
      p_intervention: 0.1,
      alpha: 0.05,
      power: 0.8,
      mean_cluster_size: 100,
      icc: 0.01,
    });
    expect(cluster).toHaveBeenCalledTimes(1);
    const definition = cluster.mock.calls[0][0] as Record<string, unknown>;
    expect(definition["mode"]).toBe("cluster_post");
    expect(definition["clusters"]).toEqual({
      control_clusters: 4,
      intervention_clusters: 4,
      mean_cluster_size: 100,
      cluster_size_distribution: { type: "fixed" },
    });

    // Sample-size cards: design effect 1.99 (3 decimals) and 4 clusters per arm.
    expect(screen.getByText("Sample size for 80% power")).toBeInTheDocument();
    const sizeCards = screen.getByTestId("size-cards");
    expect(sizeCards).toHaveTextContent("1.990");
    expect(sizeCards).toHaveTextContent("391");
    expect(within(sizeCards).getByText("4")).toBeInTheDocument();
    // Manifest-style formula line with the unrounded individual n per arm.
    const formula = screen.getByTestId("size-formula");
    expect(formula).toHaveTextContent("design_effect_1_plus_m_minus_1_icc (SPEC §14.2)");
    expect(formula).toHaveTextContent("196.221");

    // Simulated-design cards render the server summary verbatim.
    const simCards = screen.getByTestId("sim-cards");
    expect(simCards).toHaveTextContent("20.0% / 10.0%");
    expect(simCards).toHaveTextContent("1.973");
    expect(simCards).toHaveTextContent("0.099");

    // Three-analysis comparison: fixture powers, unadjusted flagged anti-conservative.
    const rows = screen.getByTestId("analysis-table").querySelectorAll("tbody tr");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Unadjusted chi-square");
    expect(rows[0]).toHaveTextContent("62.0%");
    expect(rows[0]).toHaveTextContent("anti-conservative");
    expect(rows[1]).toHaveTextContent("Design-effect adjusted chi-square");
    expect(rows[1]).toHaveTextContent("41.0%");
    expect(rows[2]).toHaveTextContent("Cluster-level t-test");
    expect(rows[2]).toHaveTextContent("38.0%");

    // Chart mounts.
    expect(screen.getByTestId("analysis-powers")).toBeInTheDocument();

    // Engine notes rendered as a note banner, carrying the anti-conservative label.
    const notes = screen.getByTestId("notes");
    expect(notes).toHaveTextContent("anti-conservative (AXIOMS §11)");

    // Manifest line from the simulation response.
    const manifest = screen.getByTestId("manifest");
    expect(manifest).toHaveTextContent("5,000 simulations");
    expect(manifest).toHaveTextContent("seed 12345");
    expect(manifest).toHaveTextContent("PCG64");
    expect(manifest).toHaveTextContent("spec 2.0.0-alpha.1");
    expect(manifest).toHaveTextContent(`input ${"d".repeat(12)}`);
  });

  it("marks the ICC field on an icc_out_of_bounds 422 from either endpoint", async () => {
    const iccError = {
      type: "ValidationError",
      code: "icc_out_of_bounds",
      message: "icc must be in [0, 1).",
      path: "icc",
      details: {},
    };
    // Both endpoints validate icc; the duplicate (same code+path) must be deduped.
    clusterSampleSize.mockRejectedValue(new ApiValidationError([iccError]));
    cluster.mockRejectedValue(new ApiValidationError([iccError]));
    render(<ClusterTrials />);
    await userEvent.click(screen.getByTestId("run-button"));

    const message = await screen.findByRole("alert");
    expect(message).toHaveTextContent("icc must be in [0, 1).");
    expect(screen.getByLabelText("ICC")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });

  it("reveals the SD field for lognormal sizes and sends it in the definition", async () => {
    clusterSampleSize.mockResolvedValue(SIZE_RESPONSE);
    cluster.mockResolvedValue(CLUSTER_RESPONSE);
    render(<ClusterTrials />);

    // Fixed sizes need no SD; the field appears only for variable-size families.
    expect(screen.queryByLabelText("Cluster size SD")).not.toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Cluster size distribution"),
      "lognormal",
    );
    const sd = screen.getByLabelText("Cluster size SD");
    expect(sd).toBeInTheDocument();

    await userEvent.type(sd, "25");
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();
    const definition = cluster.mock.calls[0][0] as Record<string, unknown>;
    expect(definition["clusters"]).toEqual({
      control_clusters: 4,
      intervention_clusters: 4,
      mean_cluster_size: 100,
      cluster_size_distribution: { type: "lognormal", sd: 25 },
    });
  });
});
