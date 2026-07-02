import { describe, expect, it } from "vitest";
import type { ApiError } from "../types";
import { buildDefinition, DEFAULT_FORM, mapErrorsToFields } from "./definition";

describe("buildDefinition", () => {
  it("produces a schema-shaped individual_binary definition", () => {
    const definition = buildDefinition(DEFAULT_FORM) as Record<string, never>;
    expect(definition["schema_version"]).toBe("icebergsim.trial.v2");
    expect(definition["mode"]).toBe("individual_binary");
    expect(definition["n_simulations"]).toBe(5000);
    expect(definition["arms"]).toEqual({
      control: { label: "Control", event_probability: 0.2 },
      intervention: { label: "Intervention", event_probability: 0.1 },
    });
    expect(definition["allocation"]).toEqual({
      total_n: 400,
      intervention_fraction: 0.5,
    });
    expect(definition["untreated_event_probability"]).toBe(0.3);
  });

  it("passes a null seed through as null (non-reproducible run)", () => {
    const definition = buildDefinition({ ...DEFAULT_FORM, randomSeed: null });
    expect(definition["random_seed"]).toBeNull();
  });
});

function error(path: string, code = "probability_out_of_bounds"): ApiError {
  return { type: "ValidationError", code, message: `bad ${path}`, path, details: {} };
}

describe("mapErrorsToFields", () => {
  it("routes engine paths to the matching form fields", () => {
    const mapped = mapErrorsToFields([
      error("arms.control.event_probability"),
      error("allocation.intervention_fraction"),
      error("alpha", "alpha_out_of_bounds"),
    ]);
    expect(mapped.fields.controlRisk).toBe("bad arms.control.event_probability");
    expect(mapped.fields.interventionFraction).toBe("bad allocation.intervention_fraction");
    expect(mapped.fields.alpha).toBe("bad alpha");
    expect(mapped.general).toHaveLength(0);
  });

  it("collects unmatched paths as general errors", () => {
    const mapped = mapErrorsToFields([
      error("imperfections.control.lost_event_risk_ratio", "derived_probability_out_of_bounds"),
    ]);
    expect(mapped.fields).toEqual({});
    expect(mapped.general).toHaveLength(1);
    expect(mapped.general[0].code).toBe("derived_probability_out_of_bounds");
  });

  it("keeps the first message when several errors hit one field", () => {
    const mapped = mapErrorsToFields([
      error("allocation.total_n", "sample_size_missing"),
      error("allocation", "sample_size_not_positive"),
    ]);
    expect(mapped.fields.totalN).toBe("bad allocation.total_n");
  });
});
