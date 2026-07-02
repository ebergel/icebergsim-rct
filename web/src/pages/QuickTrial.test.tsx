import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { SimulationResponse } from "../types";
import { QuickTrial } from "./QuickTrial";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    api: { ...original.api, simulate: vi.fn() },
  };
});

// Plotly needs a real WebGL canvas; in jsdom we only assert the charts are mounted.
vi.mock("../components/PlotlyChart", () => ({
  PlotlyChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const { api } = await import("../api");
const simulate = vi.mocked(api.simulate);

const RESPONSE: SimulationResponse = {
  manifest: {
    input_hash: "a".repeat(64),
    random_seed: 12345,
    n_simulations: 5000,
    rng_algorithm: "PCG64",
    spec_version: "2.0.0-alpha.1",
    p_value_method: "likelihood_ratio",
    alpha: 0.05,
  },
  summary: {
    mean_cer: 0.2,
    mean_eer: 0.1,
    mean_arr: 0.1,
    mean_rr: 0.5,
    mean_rrr: 0.5,
    median_arr: 0.1,
    ci95_arr_empirical: [0.03, 0.17],
    ci95_rr_empirical: [0.3, 0.82],
    power: 0.811,
    power_mcse: 0.0055,
    type_i_error: null,
    type_i_error_mcse: null,
    mean_nnt: 10.4,
    mean_nnh: null,
  },
  warnings: [],
  notes: [],
  plots: {
    rr_vs_p: { x: [0.5], y: [0.01], x_label: "rr", y_label: "p_value", alpha: 0.05 },
    arr_histogram: {
      bin_edges: [0, 0.1, 0.2],
      counts: [3, 2],
      n_defined: 5,
      n_undefined: 0,
      label: "arr",
    },
  },
};

beforeEach(() => {
  simulate.mockReset();
});

describe("QuickTrial", () => {
  it("runs a simulation and renders summary cards, manifest, and plots", async () => {
    simulate.mockResolvedValue(RESPONSE);
    render(<QuickTrial />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();
    expect(screen.getByText("81.1%")).toBeInTheDocument(); // power card
    expect(screen.getByTestId("manifest")).toHaveTextContent("PCG64");
    expect(screen.getByTestId("manifest")).toHaveTextContent("seed 12345");
    expect(screen.getByTestId("rr-vs-p")).toBeInTheDocument();
    expect(screen.getByTestId("arr-histogram")).toBeInTheDocument();

    // The definition sent to the engine came from the form defaults.
    const sent = simulate.mock.calls[0][0] as Record<string, unknown>;
    expect(sent["mode"]).toBe("individual_binary");
    expect(sent["n_simulations"]).toBe(5000);
  });

  it("highlights the offending field on a 422 validation error", async () => {
    simulate.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "probability_out_of_bounds",
          message: "arms.control.event_probability = 1.2 is outside [0, 1].",
          path: "arms.control.event_probability",
          details: {},
        },
      ]),
    );
    render(<QuickTrial />);
    await userEvent.click(screen.getByTestId("run-button"));

    const message = await screen.findByRole("alert");
    expect(message).toHaveTextContent("outside [0, 1]");
    expect(screen.getByLabelText("Control event risk")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });

  it("shows unmapped errors in the general banner", async () => {
    simulate.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "derived_probability_out_of_bounds",
          message: "Derived p_lost = 1.2 is outside [0, 1].",
          path: "imperfections.control.lost_event_risk_ratio",
          details: {},
        },
      ]),
    );
    render(<QuickTrial />);
    await userEvent.click(screen.getByTestId("run-button"));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("imperfections.control.lost_event_risk_ratio");
    expect(banner).toHaveTextContent("Derived p_lost");
  });
});
