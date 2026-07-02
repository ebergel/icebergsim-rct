import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiValidationError } from "../api";
import type { SubgroupsResponse, Summary } from "../types";
import { RiskSubgroups } from "./RiskSubgroups";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    api: { ...original.api, subgroups: vi.fn() },
  };
});

// Plotly needs a real WebGL canvas; in jsdom we only assert the chart is mounted.
vi.mock("../components/PlotlyChart", () => ({
  PlotlyChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const { api } = await import("../api");
const subgroups = vi.mocked(api.subgroups);

function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    mean_cer: 0.2,
    mean_eer: 0.1,
    mean_arr: 0.1,
    mean_rr: 0.5,
    mean_rrr: 0.5,
    median_arr: 0.1,
    ci95_arr_empirical: [0.05, 0.15],
    ci95_rr_empirical: [0.3, 0.8],
    power: 0.85,
    power_mcse: 0.006,
    type_i_error: null,
    type_i_error_mcse: null,
    mean_nnt: 10,
    mean_nnh: null,
    ...overrides,
  };
}

const RESPONSE: SubgroupsResponse = {
  manifest: {
    input_hash: "a".repeat(64),
    random_seed: 12345,
    n_simulations: 3000,
    rng_algorithm: "PCG64",
    spec_version: "2.0.0-alpha.1",
  },
  subgroups: [
    {
      id: "high_risk",
      label: "High risk",
      n_control: 100,
      n_intervention: 100,
      summary: summary({
        mean_cer: 0.3,
        mean_eer: 0.15,
        power: 0.912,
        mean_rr: 0.501,
        ci95_rr_empirical: [0.31, 0.79],
      }),
    },
    {
      id: "low_risk",
      label: "Low risk",
      n_control: 100,
      n_intervention: 100,
      summary: summary({
        mean_cer: 0.1,
        mean_eer: 0.05,
        power: 0.428,
        mean_rr: 0.497,
        ci95_rr_empirical: [0.18, 1.21],
      }),
    },
  ],
  aggregate: {
    summary: summary({
      power: 0.963,
      mean_rr: 0.499,
      ci95_rr_empirical: [0.35, 0.7],
    }),
  },
  plots: {
    forest: {
      rows: [
        {
          label: "High risk",
          rr: 0.501,
          rr_low: 0.31,
          rr_high: 0.79,
          arr: 0.15,
          arr_low: 0.08,
          arr_high: 0.22,
          is_aggregate: false,
        },
        {
          label: "Low risk",
          rr: 0.497,
          rr_low: 0.18,
          rr_high: 1.21,
          arr: 0.05,
          arr_low: -0.01,
          arr_high: 0.11,
          is_aggregate: false,
        },
        {
          label: "Aggregate",
          rr: 0.499,
          rr_low: 0.35,
          rr_high: 0.7,
          arr: 0.1,
          arr_low: 0.05,
          arr_high: 0.15,
          is_aggregate: true,
        },
      ],
    },
  },
  warnings: [],
  notes: [
    "Aggregate analyzed from per-replicate summed 2x2 counts across subgroups (SPEC §12.2).",
  ],
};

beforeEach(() => {
  subgroups.mockReset();
});

describe("RiskSubgroups", () => {
  it("simulates the family and renders the table, forest plot, and notes", async () => {
    subgroups.mockResolvedValue(RESPONSE);
    render(<RiskSubgroups />);
    await userEvent.click(screen.getByTestId("run-button"));

    expect(await screen.findByTestId("results")).toBeInTheDocument();

    // Table shows both subgroup labels with server values verbatim.
    const table = screen.getByTestId("subgroup-table");
    expect(within(table).getByText("High risk")).toBeInTheDocument();
    expect(within(table).getByText("Low risk")).toBeInTheDocument();
    expect(within(table).getByText("91.2%")).toBeInTheDocument(); // high-risk power
    expect(within(table).getByText("42.8%")).toBeInTheDocument(); // low-risk power
    expect(within(table).getByText(/0\.501 \[0\.310, 0\.790\]/)).toBeInTheDocument();

    // Aggregate row: emphasized, engine summary values, and NO client-side n summing.
    const aggregateRow = within(table).getByTestId("aggregate-row");
    expect(aggregateRow).toHaveTextContent("Aggregate");
    expect(aggregateRow).toHaveTextContent("96.3%");
    expect(aggregateRow).toHaveTextContent("0.499 [0.350, 0.700]");
    expect(aggregateRow).toHaveTextContent("—");
    expect(aggregateRow).not.toHaveTextContent("200"); // no summed 100+100

    // Forest chart mounts.
    expect(screen.getByTestId("forest")).toBeInTheDocument();

    // Notes banner carries the summed-counts note; manifest shows run provenance.
    expect(screen.getByTestId("subgroup-notes")).toHaveTextContent(
      "summed 2x2 counts across subgroups",
    );
    expect(screen.getByTestId("manifest")).toHaveTextContent("3,000 simulations");

    // The family was built with shared n_simulations/seed on every subgroup (SPEC §12.1).
    expect(subgroups).toHaveBeenCalledTimes(1);
    const family = subgroups.mock.calls[0][0] as {
      subgroups: { id: string; trial: Record<string, unknown> }[];
    };
    expect(family.subgroups).toHaveLength(2);
    expect(family.subgroups.map((s) => s.id)).toEqual(["high_risk", "low_risk"]);
    for (const subgroup of family.subgroups) {
      expect(subgroup.trial["n_simulations"]).toBe(3000);
      expect(subgroup.trial["random_seed"]).toBe(12345);
    }
  });

  it("adds a third subgroup fieldset with defaults when Add subgroup is clicked", async () => {
    render(<RiskSubgroups />);
    expect(screen.queryByText("Subgroup 3")).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("add-subgroup"));

    expect(screen.getByText("Subgroup 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Subgroup 3 id")).toHaveValue("subgroup_3");
    expect(screen.getByLabelText("Subgroup 3 total N")).toHaveValue(200);
    expect(screen.getByLabelText("Subgroup 3 control risk")).toHaveValue(0.2);
    expect(screen.getByLabelText("Subgroup 3 intervention risk")).toHaveValue(0.1);
    // The first two rows keep a working Remove button; with >1 rows none is disabled.
    expect(screen.getByLabelText("Remove subgroup 3")).toBeEnabled();
  });

  it("maps a 422 to the offending row's field and family-level errors to the banner", async () => {
    subgroups.mockRejectedValue(
      new ApiValidationError([
        {
          type: "ValidationError",
          code: "probability_out_of_bounds",
          message: "event_probability must be in [0, 1].",
          path: "subgroups[1].trial.arms.control.event_probability",
          details: {},
        },
        {
          type: "ValidationError",
          code: "subgroup_duplicate_id",
          message: "Subgroup ids must be unique.",
          path: "subgroups",
          details: {},
        },
      ]),
    );
    render(<RiskSubgroups />);
    await userEvent.click(screen.getByTestId("run-button"));

    // Row 2's control risk is flagged; row 1's is untouched.
    const badField = await screen.findByLabelText("Subgroup 2 control risk");
    expect(badField).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Subgroup 1 control risk")).not.toHaveAttribute(
      "aria-invalid",
    );

    // Family-level duplicate-id error lands in the general banner.
    const alerts = screen.getAllByRole("alert");
    const banner = alerts.find((el) =>
      el.textContent?.includes("Subgroup ids must be unique."),
    );
    expect(banner).toBeDefined();
    expect(banner).toHaveTextContent("subgroups");

    expect(screen.queryByTestId("results")).not.toBeInTheDocument();
  });
});
