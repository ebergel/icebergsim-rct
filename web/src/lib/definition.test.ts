import { describe, expect, it } from "vitest";
import type { ApiError } from "../types";
import {
  buildDefinition,
  buildPragmaticDefinition,
  DEFAULT_FORM,
  IDEAL_IMPERFECTIONS,
  mapErrorsToFields,
  mapImperfectionErrors,
  powerCurveSizes,
} from "./definition";

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

describe("buildPragmaticDefinition", () => {
  it("adds wire-format imperfection blocks for both arms", () => {
    const definition = buildPragmaticDefinition(
      DEFAULT_FORM,
      { ...IDEAL_IMPERFECTIONS, lossProbability: 0.1, noncomplianceProbability: 0.2 },
      IDEAL_IMPERFECTIONS,
    );
    expect(definition["imperfections"]).toEqual({
      control: {
        loss_probability: 0.1,
        lost_event_risk_ratio: 1,
        noncompliance_probability: 0.2,
        crossover_probability: 0,
        ascertainment_event_probability: 1,
        ascertainment_nonevent_false_positive_probability: 0,
      },
      intervention: {
        loss_probability: 0,
        lost_event_risk_ratio: 1,
        noncompliance_probability: 0,
        crossover_probability: 0,
        ascertainment_event_probability: 1,
        ascertainment_nonevent_false_positive_probability: 0,
      },
    });
  });
});

describe("mapImperfectionErrors", () => {
  it("routes per-arm imperfection paths to arm fields", () => {
    const mapped = mapImperfectionErrors([
      error("imperfections.control.lost_event_risk_ratio", "derived_probability_out_of_bounds"),
      error("imperfections.intervention.loss_probability"),
      error("alpha", "alpha_out_of_bounds"),
    ]);
    expect(mapped.control.lostEventRiskRatio).toContain("lost_event_risk_ratio");
    expect(mapped.intervention.lossProbability).toContain("loss_probability");
    expect(mapped.rest).toHaveLength(1);
    expect(mapped.rest[0].path).toBe("alpha");
  });
});

describe("powerCurveSizes", () => {
  it("brackets the formula size with even, deduplicated, sorted totals", () => {
    expect(powerCurveSizes(394)).toEqual([198, 296, 394, 492, 592]);
  });

  it("never goes below a simulable size", () => {
    expect(powerCurveSizes(4)[0]).toBeGreaterThanOrEqual(4);
  });
});

describe("ratioToInterventionFraction", () => {
  it("converts allocation ratios to fractions", async () => {
    const { ratioToInterventionFraction } = await import("./definition");
    expect(ratioToInterventionFraction(1)).toBe(0.5);
    expect(ratioToInterventionFraction(2)).toBeCloseTo(2 / 3, 12);
  });
});
