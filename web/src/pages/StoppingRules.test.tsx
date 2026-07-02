import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { StoppingResponse } from "../types";
import { StoppingRules } from "./StoppingRules";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    api: { ...original.api, stopping: vi.fn() },
  };
});

// Plotly needs a real WebGL canvas; in jsdom we only assert the chart is mounted.
vi.mock("../components/PlotlyChart", () => ({
  PlotlyChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const { api } = await import("../api");
const stopping = vi.mocked(api.stopping);

// Peto plan resolved by the engine: 3 interims at p<0.001, final at p<0.05, equally
// spaced information fractions for total N 800 (400/400 per arm at the final analysis).
const RESPONSE: StoppingResponse = {
  manifest: {
    input_hash: "c".repeat(64),
    random_seed: 12345,
    n_simulations: 5000,
    rng_algorithm: "PCG64",
    spec_version: "2.0.0-alpha.1",
  },
  plan: {
    rule: "peto",
    n_interims: 3,
    information_fractions: [0.25, 0.5, 0.75],
    interim_p_thresholds: [0.001, 0.001, 0.001],
    final_p_threshold: 0.05,
    enabled: true,
    stop_for: "benefit_or_harm",
    minimum_total_events: null,
  },
  look_sample_sizes: [
    [100, 100],
    [200, 200],
    [300, 300],
    [400, 400],
  ],
  summary: {
    proportion_stopped_any: 0.182,
    proportion_stopped_benefit: 0.176,
    proportion_stopped_harm: 0.006,
    proportion_stopped_by_look: [0.031, 0.072, 0.079],
    mean_fraction_at_stop: 0.582,
    final_power_including_stops: 0.914,
    type_i_error_including_stops: null,
    type_i_error_mcse: null,
  },
  plots: {
    stop_by_look: {
      looks: [1, 2, 3],
      information_fractions: [0.25, 0.5, 0.75],
      proportions: [0.031, 0.072, 0.079],
      proportion_reaching_final: 0.818,
    },
  },
};

beforeEach(() => {
  stopping.mockReset();
});

describe("StoppingRules", () => {
  it("runs the simulation and renders plan, summary cards, look table, and chart", async () => {
    stopping.mockResolvedValue(RESPONSE);
    render(<StoppingRules />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();

    // Resolved plan rendered verbatim: rule, interim thresholds, final threshold, fractions.
    const plan = screen.getByTestId("plan");
    expect(plan).toHaveTextContent("peto");
    expect(plan).toHaveTextContent("0.001, 0.001, 0.001");
    expect(plan).toHaveTextContent("final p threshold 0.05");
    expect(plan).toHaveTextContent("25%, 50%, 75%");

    // Summary cards show server percentages verbatim.
    const cards = screen.getByTestId("summary-cards");
    expect(cards).toHaveTextContent("18.2%"); // stopped early
    expect(cards).toHaveTextContent("17.6% / 0.6%"); // benefit / harm
    expect(cards).toHaveTextContent("58.2%"); // mean information fraction at stop
    expect(cards).toHaveTextContent("91.4%"); // power including stops
    // Type I card absent when the null simulation was not requested.
    expect(cards).not.toHaveTextContent("Type I incl. stops");

    // Look table: 3 interim rows + 1 final row.
    const rows = screen.getByTestId("look-table").querySelectorAll("tbody tr");
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent("look 1");
    expect(rows[0]).toHaveTextContent("100"); // cumulative n at look 1
    expect(rows[0]).toHaveTextContent("0.001");
    expect(rows[0]).toHaveTextContent("3.1% stopped here");
    expect(rows[3]).toHaveTextContent("final");
    expect(rows[3]).toHaveTextContent("400");
    expect(rows[3]).toHaveTextContent("0.05");
    expect(rows[3]).toHaveTextContent("81.8% reached final analysis");

    // Chart mounts.
    expect(screen.getByTestId("stop-by-look")).toBeInTheDocument();

    // Definition sent with the page defaults: total N 800 and an enabled peto plan.
    expect(stopping).toHaveBeenCalledTimes(1);
    const definition = stopping.mock.calls[0][0] as Record<string, unknown>;
    expect((definition["allocation"] as Record<string, unknown>)["total_n"]).toBe(800);
    expect(definition["stopping"]).toEqual({
      enabled: true,
      rule: "peto",
      n_interims: 3,
      stop_for: "benefit_or_harm",
    });
    expect(stopping.mock.calls[0][1]).toEqual({ includeTypeIError: false });
  });

  it("marks the custom thresholds input on a stopping.interim_p_thresholds 422", async () => {
    stopping.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "stopping_threshold_length_mismatch",
          message: "interim_p_thresholds must have length n_interims (3).",
          path: "stopping.interim_p_thresholds",
          details: {},
        },
      ]),
    );
    render(<StoppingRules />);

    await userEvent.selectOptions(screen.getByLabelText("Stopping rule"), "custom");
    const thresholds = screen.getByLabelText("Interim p thresholds");
    await userEvent.type(thresholds, "0.001, 0.004");
    await userEvent.click(screen.getByTestId("run-button"));

    const message = await screen.findByRole("alert");
    expect(message).toHaveTextContent("must have length n_interims");
    expect(thresholds).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();

    // The parsed list (not the raw text) went into the definition.
    const definition = stopping.mock.calls[0][0] as Record<string, unknown>;
    expect((definition["stopping"] as Record<string, unknown>)["interim_p_thresholds"]).toEqual([
      0.001, 0.004,
    ]);
  });

  it("sends includeTypeIError when the checkbox is on and renders the Type I card", async () => {
    stopping.mockResolvedValue({
      ...RESPONSE,
      summary: {
        ...RESPONSE.summary,
        type_i_error_including_stops: 0.048,
        type_i_error_mcse: 0.003,
      },
    });
    render(<StoppingRules />);

    await userEvent.click(screen.getByTestId("type-i-toggle"));
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();
    expect(stopping).toHaveBeenCalledWith(expect.anything(), { includeTypeIError: true });
    const cards = screen.getByTestId("summary-cards");
    expect(cards).toHaveTextContent("Type I incl. stops");
    expect(cards).toHaveTextContent("4.8% ± 0.30%");
  });

  it("routes unmapped 422 errors to the base fields and the general banner", async () => {
    stopping.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "alpha_out_of_range",
          message: "alpha must be in (0, 1).",
          path: "alpha",
          details: {},
        },
        {
          type: "ValidationError",
          code: "mode_unsupported",
          message: "stopping requires individual_binary mode.",
          path: "mode",
          details: {},
        },
      ]),
    );
    render(<StoppingRules />);
    await userEvent.click(screen.getByTestId("run-button"));

    // alpha maps to its field; the mode error has no field and lands in the banner.
    expect(await screen.findByText("alpha must be in (0, 1).")).toBeInTheDocument();
    expect(screen.getByLabelText("Alpha")).toHaveAttribute("aria-invalid", "true");
    const banners = screen.getAllByRole("alert");
    const general = banners.find((b) => b.textContent?.includes("individual_binary"));
    expect(general).toBeDefined();
    expect(general).toHaveTextContent("mode");
  });
});
