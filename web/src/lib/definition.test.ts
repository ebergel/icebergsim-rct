import { describe, expect, it } from "vitest";
import type { ApiError } from "../types";
import {
  buildClusterDefinition,
  buildDefinition,
  buildPragmaticDefinition,
  DEFAULT_CLUSTER_FORM,
  mapClusterErrors,
  buildStoppingDefinition,
  buildSubgroupFamily,
  DEFAULT_STOPPING,
  DEFAULT_SUBGROUP_ROWS,
  DEFAULT_SUBGROUP_SHARED,
  mapStoppingErrors,
  mapSubgroupErrors,
  parseNumberList,
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

describe("buildStoppingDefinition", () => {
  it("attaches a named-rule stopping block", () => {
    const definition = buildStoppingDefinition(DEFAULT_FORM, DEFAULT_STOPPING);
    expect(definition["stopping"]).toEqual({
      enabled: true,
      rule: "peto",
      n_interims: 3,
      stop_for: "benefit_or_harm",
    });
  });

  it("includes custom thresholds only for the custom rule", () => {
    const definition = buildStoppingDefinition(DEFAULT_FORM, {
      ...DEFAULT_STOPPING,
      rule: "custom",
      nInterims: 2,
      interimPThresholds: [0.001, 0.01],
      finalPThreshold: 0.045,
      minimumTotalEvents: 20,
    });
    expect(definition["stopping"]).toEqual({
      enabled: true,
      rule: "custom",
      n_interims: 2,
      stop_for: "benefit_or_harm",
      minimum_total_events: 20,
      interim_p_thresholds: [0.001, 0.01],
      final_p_threshold: 0.045,
    });
  });
});

describe("parseNumberList", () => {
  it("parses comma-separated thresholds", () => {
    expect(parseNumberList("0.001, 0.01,0.02")).toEqual([0.001, 0.01, 0.02]);
  });
  it("returns null for empty or invalid input", () => {
    expect(parseNumberList("")).toBeNull();
    expect(parseNumberList("0.1, abc")).toBeNull();
  });
});

describe("mapStoppingErrors", () => {
  it("routes stopping paths to stopping fields and the rest onward", () => {
    const mapped = mapStoppingErrors([
      error("stopping.interim_p_thresholds", "stopping_threshold_length_mismatch"),
      error("alpha", "alpha_out_of_bounds"),
    ]);
    expect(mapped.stopping.interimPThresholds).toContain("stopping.interim_p_thresholds");
    expect(mapped.rest).toHaveLength(1);
    expect(mapped.rest[0].path).toBe("alpha");
  });
});

describe("buildSubgroupFamily", () => {
  it("builds one trial per row sharing simulation policy", () => {
    const family = buildSubgroupFamily(DEFAULT_SUBGROUP_SHARED, DEFAULT_SUBGROUP_ROWS);
    const subgroups = family["subgroups"] as Record<string, unknown>[];
    expect(subgroups).toHaveLength(2);
    expect(subgroups[0]["id"]).toBe("high_risk");
    const trial = subgroups[0]["trial"] as Record<string, unknown>;
    expect(trial["n_simulations"]).toBe(3000);
    expect(trial["random_seed"]).toBe(12345);
    const arms = trial["arms"] as Record<string, Record<string, unknown>>;
    expect(arms["control"]["event_probability"]).toBe(0.3);
    const secondTrial = subgroups[1]["trial"] as Record<string, unknown>;
    expect(secondTrial["n_simulations"]).toBe(3000); // SPEC §12.1 same policy
  });
});

describe("mapSubgroupErrors", () => {
  it("routes indexed trial paths to row fields", () => {
    const mapped = mapSubgroupErrors([
      error("subgroups[1].trial.arms.control.event_probability"),
      error("subgroups[0].id", "missing_field"),
      error("subgroups", "subgroup_duplicate_id"),
    ]);
    expect(mapped.rows[1]?.controlRisk).toBeDefined();
    expect(mapped.rows[0]?.id).toBeDefined();
    expect(mapped.general).toHaveLength(1);
    expect(mapped.general[0].code).toBe("subgroup_duplicate_id");
  });
});

describe("buildClusterDefinition", () => {
  it("builds a cluster_post definition from the form", () => {
    const definition = buildClusterDefinition(DEFAULT_CLUSTER_FORM);
    expect(definition["mode"]).toBe("cluster_post");
    expect(definition["icc"]).toBe(0.01);
    expect(definition["clusters"]).toEqual({
      control_clusters: 4,
      intervention_clusters: 4,
      mean_cluster_size: 100,
      cluster_size_distribution: { type: "fixed" },
    });
  });

  it("includes sd only for variable size distributions", () => {
    const definition = buildClusterDefinition({
      ...DEFAULT_CLUSTER_FORM,
      sizeType: "lognormal",
      sizeSd: 25,
    });
    const clusters = definition["clusters"] as Record<string, unknown>;
    expect(clusters["cluster_size_distribution"]).toEqual({ type: "lognormal", sd: 25 });
  });
});

describe("mapClusterErrors", () => {
  it("routes cluster paths to fields and the rest to the banner", () => {
    const mapped = mapClusterErrors([
      error("icc", "icc_out_of_bounds"),
      error("clusters.cluster_size_distribution.sd", "cluster_size_sd_required"),
      error("mode", "invalid_mode"),
    ]);
    expect(mapped.fields.icc).toBeDefined();
    expect(mapped.fields.sizeSd).toBeDefined();
    expect(mapped.general).toHaveLength(1);
    expect(mapped.general[0].code).toBe("invalid_mode");
  });
});
