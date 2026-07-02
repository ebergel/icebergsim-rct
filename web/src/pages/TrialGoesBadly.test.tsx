import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { SimulationResponse, TrialDefinition } from "../types";
import { TrialGoesBadly } from "./TrialGoesBadly";

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

const MINUS = "−";

const IDEAL_RESPONSE: SimulationResponse = {
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
    power: 0.81,
    power_mcse: 0.0055,
    type_i_error: null,
    type_i_error_mcse: null,
    mean_nnt: 10.0,
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

const PRAGMATIC_RESPONSE: SimulationResponse = {
  ...IDEAL_RESPONSE,
  manifest: { ...IDEAL_RESPONSE.manifest, input_hash: "b".repeat(64) },
  summary: {
    ...IDEAL_RESPONSE.summary,
    mean_cer: 0.18,
    mean_eer: 0.15,
    mean_arr: 0.03,
    mean_rr: 0.83,
    mean_rrr: 0.17,
    power: 0.34,
    mean_nnt: 33.3,
  },
  warnings: ["Attrition exceeds 20% in the control arm."],
  notes: ["Analysis population: intention-to-treat."],
  plots: {
    ...IDEAL_RESPONSE.plots,
    arr_histogram: {
      bin_edges: [-0.1, 0, 0.1],
      counts: [1, 4],
      n_defined: 5,
      n_undefined: 0,
      label: "arr",
    },
  },
};

function respondById(definition: TrialDefinition): Promise<SimulationResponse> {
  return Promise.resolve(
    definition["id"] === "pragmatic_trial" ? PRAGMATIC_RESPONSE : IDEAL_RESPONSE,
  );
}

beforeEach(() => {
  simulate.mockReset();
});

describe("TrialGoesBadly", () => {
  it("simulates both scenarios and renders the side-by-side comparison", async () => {
    simulate.mockImplementation(respondById);
    render(<TrialGoesBadly />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();

    // Both scenarios were submitted (ideal + pragmatic definitions).
    expect(simulate).toHaveBeenCalledTimes(2);
    const sentIds = simulate.mock.calls.map(
      ([definition]) => (definition as Record<string, unknown>)["id"],
    );
    expect(sentIds).toContain("quick_trial");
    expect(sentIds).toContain("pragmatic_trial");
    const pragmaticSent = simulate.mock.calls
      .map(([definition]) => definition as Record<string, unknown>)
      .find((d) => d["id"] === "pragmatic_trial");
    expect(pragmaticSent?.["imperfections"]).toMatchObject({
      control: { loss_probability: 0, lost_event_risk_ratio: 1 },
      intervention: { ascertainment_event_probability: 1 },
    });

    // Comparison table: both powers and a signed negative delta (display-only).
    const table = within(screen.getByTestId("comparison-table"));
    const powerRow = table.getByRole("row", { name: /^Power/ });
    expect(powerRow).toHaveTextContent("81.0%");
    expect(powerRow).toHaveTextContent("34.0%");
    expect(powerRow).toHaveTextContent(`${MINUS}47.0 pts`);
    const nntRow = table.getByRole("row", { name: /^NNT/ });
    expect(nntRow).toHaveTextContent("10.0");
    expect(nntRow).toHaveTextContent("33.3");
    expect(nntRow).toHaveTextContent("+23.3");

    // Prominent callout repeats the power drop.
    expect(screen.getByTestId("power-callout")).toHaveTextContent(
      `Power: 81.0% → 34.0% (Δ ${MINUS}47.0 points)`,
    );

    // Overlaid ARR histogram chart mounts.
    expect(screen.getByTestId("arr-comparison")).toBeInTheDocument();

    // Pragmatic warnings, notes, and manifest render.
    expect(screen.getByTestId("pragmatic-warnings")).toHaveTextContent(
      "Attrition exceeds 20% in the control arm.",
    );
    expect(screen.getByTestId("pragmatic-notes")).toHaveTextContent(
      "Analysis population: intention-to-treat.",
    );
    expect(screen.getByTestId("manifest")).toHaveTextContent("bbbbbbbbbbbb");
  });

  it("marks the control-arm loss field on an imperfection-path 422", async () => {
    simulate.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "probability_out_of_bounds",
          message: "imperfections.control.loss_probability = 1.4 is outside [0, 1].",
          path: "imperfections.control.loss_probability",
          details: {},
        },
        {
          type: "ValidationError",
          code: "probability_out_of_bounds",
          message: "arms.control.event_probability = 1.2 is outside [0, 1].",
          path: "arms.control.event_probability",
          details: {},
        },
      ]),
    );
    render(<TrialGoesBadly />);
    await userEvent.click(screen.getByTestId("run-button"));

    const message = await screen.findAllByRole("alert");
    expect(message.length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Control loss probability")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    // Intervention arm's twin field stays untouched.
    expect(screen.getByLabelText("Intervention loss probability")).not.toHaveAttribute(
      "aria-invalid",
    );
    // Base-field paths still map through mapErrorsToFields.
    expect(screen.getByLabelText("Control event risk")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });

  it("shows unmapped 422 errors in the general banner", async () => {
    simulate.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "unsupported_mode",
          message: "Mode 'cluster' is not supported here.",
          path: "mode",
          details: {},
        },
      ]),
    );
    render(<TrialGoesBadly />);
    await userEvent.click(screen.getByTestId("run-button"));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("mode");
    expect(banner).toHaveTextContent("Mode 'cluster' is not supported here.");
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });
});
