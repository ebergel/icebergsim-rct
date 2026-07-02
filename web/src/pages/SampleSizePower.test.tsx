import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { PowerCurveResponse, SampleSizeResponse } from "../types";
import { SampleSizePower } from "./SampleSizePower";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    api: { ...original.api, sampleSizeTwoArm: vi.fn(), powerCurve: vi.fn() },
  };
});

// Plotly needs a real WebGL canvas; in jsdom we only assert the chart is mounted.
vi.mock("../components/PlotlyChart", () => ({
  PlotlyChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const { api } = await import("../api");
const sampleSizeTwoArm = vi.mocked(api.sampleSizeTwoArm);
const powerCurve = vi.mocked(api.powerCurve);

// Canonical formula result for CER 0.2 vs EER 0.1, alpha 0.05, power 0.8, ratio 1.
const SIZE: SampleSizeResponse = {
  n_control: 197,
  n_intervention: 197,
  n_total: 394,
  unrounded_n_control: 196.22199335872716,
  unrounded_n_intervention: 196.22199335872716,
  allocation_ratio_intervention_to_control: 1,
  formula: "normal_approximation_two_proportions (SPEC §10.1/§10.2)",
};

const CURVE: PowerCurveResponse = {
  input_hash: "b".repeat(64),
  random_seed: 12345,
  rng_algorithm: "PCG64",
  spec_version: "2.0.0-alpha.1",
  points: [
    { total_n: 198, n_control: 99, n_intervention: 99, power: 0.512, power_mcse: 0.011 },
    { total_n: 296, n_control: 148, n_intervention: 148, power: 0.678, power_mcse: 0.01 },
    { total_n: 394, n_control: 197, n_intervention: 197, power: 0.802, power_mcse: 0.009 },
    { total_n: 492, n_control: 246, n_intervention: 246, power: 0.884, power_mcse: 0.007 },
    { total_n: 592, n_control: 296, n_intervention: 296, power: 0.931, power_mcse: 0.006 },
  ],
  plot: {
    total_n: [198, 296, 394, 492, 592],
    power: [0.512, 0.678, 0.802, 0.884, 0.931],
    power_mcse: [0.011, 0.01, 0.009, 0.007, 0.006],
  },
};

beforeEach(() => {
  sampleSizeTwoArm.mockReset();
  powerCurve.mockReset();
});

describe("SampleSizePower", () => {
  it("runs formula then power curve and renders cards, chart, and points", async () => {
    sampleSizeTwoArm.mockResolvedValue(SIZE);
    powerCurve.mockResolvedValue(CURVE);
    render(<SampleSizePower />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();
    // Server values rendered verbatim.
    expect(screen.getByText("394")).toBeInTheDocument(); // total N card
    expect(screen.getByText("197 / 197")).toBeInTheDocument(); // per-arm card
    expect(screen.getByText("196.222")).toBeInTheDocument(); // unrounded n, 3 decimals
    expect(screen.getByTestId("formula")).toHaveTextContent(
      "normal_approximation_two_proportions",
    );

    // Step 1 was called with the form defaults.
    expect(sampleSizeTwoArm).toHaveBeenCalledWith({
      p_control: 0.2,
      p_intervention: 0.1,
      alpha: 0.05,
      power: 0.8,
      alternative: "two_sided",
      allocation_ratio_intervention_to_control: 1,
    });

    // Step 2 was called with sizes bracketing the formula N: powerCurveSizes(394).
    expect(powerCurve).toHaveBeenCalledTimes(1);
    expect(powerCurve.mock.calls[0][1]).toEqual([198, 296, 394, 492, 592]);
    const definition = powerCurve.mock.calls[0][0] as Record<string, unknown>;
    expect(definition["n_simulations"]).toBe(2000);
    expect((definition["allocation"] as Record<string, unknown>)["total_n"]).toBe(394);
    // untreatedRisk is pinned to the control risk (no noncompliance modeled here).
    expect(definition["untreated_event_probability"]).toBe(0.2);

    // Chart mounts and the points list shows server power values.
    expect(screen.getByTestId("power-curve")).toBeInTheDocument();
    const points = screen.getByTestId("power-points");
    expect(points).toHaveTextContent("80.2%");
    expect(points).toHaveTextContent("total n 592");
  });

  it("marks the intervention risk field on a 422 and skips the power curve", async () => {
    sampleSizeTwoArm.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "effect_size_zero",
          message: "p_intervention must differ from p_control.",
          path: "p_intervention",
          details: {},
        },
      ]),
    );
    render(<SampleSizePower />);
    await userEvent.click(screen.getByTestId("run-button"));

    const message = await screen.findByRole("alert");
    expect(message).toHaveTextContent("must differ from p_control");
    expect(screen.getByLabelText("Intervention event risk")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(powerCurve).not.toHaveBeenCalled();
    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });

  it("simulates ideal AND pragmatic curves when pragmatic assumptions are enabled", async () => {
    sampleSizeTwoArm.mockResolvedValue(SIZE);
    powerCurve.mockResolvedValue(CURVE);
    render(<SampleSizePower />);

    await userEvent.click(screen.getByTestId("pragmatic-toggle"));
    await userEvent.clear(screen.getByLabelText("Control loss probability"));
    await userEvent.type(screen.getByLabelText("Control loss probability"), "0.1");
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();
    expect(powerCurve).toHaveBeenCalledTimes(2);
    const pragmaticDefinition = powerCurve.mock.calls[1][0] as Record<string, unknown>;
    const imperfections = pragmaticDefinition["imperfections"] as Record<
      string,
      Record<string, number>
    >;
    expect(imperfections["control"]["loss_probability"]).toBeCloseTo(0.1, 12);
    expect(imperfections["intervention"]["loss_probability"]).toBe(0);
    // Both curves use the same bracketing sizes.
    expect(powerCurve.mock.calls[1][1]).toEqual(powerCurve.mock.calls[0][1]);
    // Points list reports both powers.
    expect(screen.getByTestId("power-points")).toHaveTextContent("pragmatic power");
  });

  it("shows power-curve 422 errors in the general banner but keeps the formula cards", async () => {
    sampleSizeTwoArm.mockResolvedValue(SIZE);
    powerCurve.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "total_n_not_even",
          message: "total_sample_sizes[0] must be even.",
          path: "total_sample_sizes",
          details: {},
        },
      ]),
    );
    render(<SampleSizePower />);
    await userEvent.click(screen.getByTestId("run-button"));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("total_sample_sizes");
    expect(banner).toHaveTextContent("must be even");
    // Formula result still shown; chart absent.
    expect(screen.getByTestId("results")).toBeInTheDocument();
    expect(screen.getByText("394")).toBeInTheDocument();
    expect(screen.queryByTestId("power-curve")).not.toBeInTheDocument();
  });
});
