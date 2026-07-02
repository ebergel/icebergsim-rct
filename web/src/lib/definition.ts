// Pure form-model logic for the Quick Trial page (SPEC §17.1). Building the definition and
// mapping validation-error paths to form fields lives here so it is unit-testable.

import type { ApiError, TrialDefinition } from "../types";

export interface QuickTrialForm {
  totalN: number;
  interventionFraction: number;
  controlRisk: number;
  interventionRisk: number;
  untreatedRisk: number;
  alpha: number;
  nSimulations: number;
  randomSeed: number | null;
}

export const DEFAULT_FORM: QuickTrialForm = {
  // Historical ICEBERGSIM defaults (traceability notes: vars.cts).
  totalN: 400,
  interventionFraction: 0.5,
  controlRisk: 0.2,
  interventionRisk: 0.1,
  untreatedRisk: 0.3,
  alpha: 0.05,
  nSimulations: 5000,
  randomSeed: 12345,
};

export function buildDefinition(form: QuickTrialForm): TrialDefinition {
  return {
    schema_version: "icebergsim.trial.v2",
    id: "quick_trial",
    label: "Quick two-arm trial",
    mode: "individual_binary",
    n_simulations: form.nSimulations,
    random_seed: form.randomSeed,
    alpha: form.alpha,
    arms: {
      control: { label: "Control", event_probability: form.controlRisk },
      intervention: { label: "Intervention", event_probability: form.interventionRisk },
    },
    allocation: {
      total_n: form.totalN,
      intervention_fraction: form.interventionFraction,
    },
    untreated_event_probability: form.untreatedRisk,
  };
}

// Engine error path -> form field. Prefix matching so nested paths land on their field.
const PATH_TO_FIELD: [string, keyof QuickTrialForm][] = [
  ["arms.control.event_probability", "controlRisk"],
  ["arms.intervention.event_probability", "interventionRisk"],
  ["untreated_event_probability", "untreatedRisk"],
  ["allocation.total_n", "totalN"],
  ["allocation.intervention_fraction", "interventionFraction"],
  ["allocation", "totalN"],
  ["alpha", "alpha"],
  ["n_simulations", "nSimulations"],
  ["random_seed", "randomSeed"],
];

export interface MappedErrors {
  fields: Partial<Record<keyof QuickTrialForm, string>>;
  general: ApiError[];
}

export function mapErrorsToFields(errors: ApiError[]): MappedErrors {
  const fields: MappedErrors["fields"] = {};
  const general: ApiError[] = [];
  for (const error of errors) {
    const match = PATH_TO_FIELD.find(([prefix]) => error.path.startsWith(prefix));
    if (match && fields[match[1]] === undefined) {
      fields[match[1]] = error.message;
    } else if (!match) {
      general.push(error);
    }
  }
  return { fields, general };
}

// --- imperfections (SPEC §17.2 "what if the trial goes badly?") ------------------------------

export interface ImperfectionForm {
  lossProbability: number;
  lostEventRiskRatio: number;
  noncomplianceProbability: number;
  crossoverProbability: number;
  ascertainmentEventProbability: number;
  ascertainmentFalsePositiveProbability: number;
}

// Engine defaults (SPEC §4.2): a perfect arm.
export const IDEAL_IMPERFECTIONS: ImperfectionForm = {
  lossProbability: 0,
  lostEventRiskRatio: 1,
  noncomplianceProbability: 0,
  crossoverProbability: 0,
  ascertainmentEventProbability: 1,
  ascertainmentFalsePositiveProbability: 0,
};

const IMPERFECTION_KEYS: [keyof ImperfectionForm, string][] = [
  ["lossProbability", "loss_probability"],
  ["lostEventRiskRatio", "lost_event_risk_ratio"],
  ["noncomplianceProbability", "noncompliance_probability"],
  ["crossoverProbability", "crossover_probability"],
  ["ascertainmentEventProbability", "ascertainment_event_probability"],
  ["ascertainmentFalsePositiveProbability", "ascertainment_nonevent_false_positive_probability"],
];

export function buildPragmaticDefinition(
  form: QuickTrialForm,
  control: ImperfectionForm,
  intervention: ImperfectionForm,
): TrialDefinition {
  return {
    ...buildDefinition(form),
    id: "pragmatic_trial",
    label: "Pragmatic trial with imperfections",
    imperfections: {
      control: imperfectionsPayload(control),
      intervention: imperfectionsPayload(intervention),
    },
  };
}

function imperfectionsPayload(form: ImperfectionForm): Record<string, number> {
  return Object.fromEntries(IMPERFECTION_KEYS.map(([key, wire]) => [wire, form[key]]));
}

export interface MappedImperfectionErrors {
  control: Partial<Record<keyof ImperfectionForm, string>>;
  intervention: Partial<Record<keyof ImperfectionForm, string>>;
  rest: ApiError[];
}

export function mapImperfectionErrors(errors: ApiError[]): MappedImperfectionErrors {
  const mapped: MappedImperfectionErrors = { control: {}, intervention: {}, rest: [] };
  for (const error of errors) {
    const match = error.path.match(/^imperfections\.(control|intervention)\.(\w+)/);
    const key = match && IMPERFECTION_KEYS.find(([, wire]) => wire === match[2])?.[0];
    if (match && key) {
      const arm = match[1] as "control" | "intervention";
      if (mapped[arm][key] === undefined) mapped[arm][key] = error.message;
    } else {
      mapped.rest.push(error);
    }
  }
  return mapped;
}

// --- power curve sizes (SPEC §17.3) -----------------------------------------------------------

// Sample sizes bracketing a formula result, for the power-over-n chart. Presentation
// choice only — the power values themselves come from the engine.
export function powerCurveSizes(totalN: number): number[] {
  const fractions = [0.5, 0.75, 1.0, 1.25, 1.5];
  const sizes = fractions.map((f) => Math.max(4, 2 * Math.round((totalN * f) / 2)));
  return [...new Set(sizes)].sort((a, b) => a - b);
}

// Allocation ratio r = n_intervention / n_control <-> intervention fraction (SPEC §10.2/§4.1).
export function ratioToInterventionFraction(ratio: number): number {
  return ratio / (1 + ratio);
}

// --- stopping rules (SPEC §11, §17 stopping workflow) ------------------------------------------

export interface StoppingForm {
  rule: "peto" | "pocock" | "obrien_fleming" | "custom";
  nInterims: number;
  stopFor: "benefit" | "harm" | "benefit_or_harm";
  minimumTotalEvents: number | null;
  // Custom rule only; comma-separated in the UI, parsed via parseNumberList.
  interimPThresholds: number[] | null;
  finalPThreshold: number | null;
}

export const DEFAULT_STOPPING: StoppingForm = {
  rule: "peto",
  nInterims: 3,
  stopFor: "benefit_or_harm",
  minimumTotalEvents: null,
  interimPThresholds: null,
  finalPThreshold: null,
};

export function parseNumberList(text: string): number[] | null {
  const parts = text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (parts.length === 0) return null;
  const numbers = parts.map(Number);
  return numbers.some(Number.isNaN) ? null : numbers;
}

export function buildStoppingDefinition(
  form: QuickTrialForm,
  stopping: StoppingForm,
): TrialDefinition {
  const block: Record<string, unknown> = {
    enabled: true,
    rule: stopping.rule,
    n_interims: stopping.nInterims,
    stop_for: stopping.stopFor,
  };
  if (stopping.minimumTotalEvents !== null) {
    block["minimum_total_events"] = stopping.minimumTotalEvents;
  }
  if (stopping.rule === "custom") {
    block["interim_p_thresholds"] = stopping.interimPThresholds;
    block["final_p_threshold"] = stopping.finalPThreshold;
  }
  return {
    ...buildDefinition(form),
    id: "stopping_trial",
    label: "Trial with interim stopping",
    stopping: block,
  };
}

const STOPPING_PATH_TO_FIELD: [string, keyof StoppingForm][] = [
  ["stopping.rule", "rule"],
  ["stopping.n_interims", "nInterims"],
  ["stopping.stop_for", "stopFor"],
  ["stopping.minimum_total_events", "minimumTotalEvents"],
  ["stopping.interim_p_thresholds", "interimPThresholds"],
  ["stopping.final_p_threshold", "finalPThreshold"],
  ["stopping.information_fractions", "nInterims"],
];

export interface MappedStoppingErrors {
  stopping: Partial<Record<keyof StoppingForm, string>>;
  rest: ApiError[];
}

export function mapStoppingErrors(errors: ApiError[]): MappedStoppingErrors {
  const stopping: MappedStoppingErrors["stopping"] = {};
  const rest: ApiError[] = [];
  for (const error of errors) {
    const match = STOPPING_PATH_TO_FIELD.find(([prefix]) => error.path.startsWith(prefix));
    if (match && stopping[match[1]] === undefined) {
      stopping[match[1]] = error.message;
    } else if (!match) {
      rest.push(error);
    }
  }
  return { stopping, rest };
}

// --- risk subgroups (SPEC §12, §17.4) -----------------------------------------------------------

export interface SubgroupRowForm {
  id: string;
  label: string;
  totalN: number;
  controlRisk: number;
  interventionRisk: number;
}

export interface SubgroupSharedForm {
  alpha: number;
  nSimulations: number;
  randomSeed: number | null;
  untreatedRisk: number;
}

export const DEFAULT_SUBGROUP_ROWS: SubgroupRowForm[] = [
  { id: "high_risk", label: "High risk", totalN: 200, controlRisk: 0.3, interventionRisk: 0.15 },
  { id: "low_risk", label: "Low risk", totalN: 200, controlRisk: 0.1, interventionRisk: 0.05 },
];

export const DEFAULT_SUBGROUP_SHARED: SubgroupSharedForm = {
  alpha: 0.05,
  nSimulations: 3000,
  randomSeed: 12345,
  untreatedRisk: 0.3,
};

export function buildSubgroupFamily(
  shared: SubgroupSharedForm,
  rows: SubgroupRowForm[],
): Record<string, unknown> {
  return {
    subgroups: rows.map((row) => ({
      id: row.id,
      label: row.label,
      weight: null,
      trial: buildDefinition({
        totalN: row.totalN,
        interventionFraction: 0.5,
        controlRisk: row.controlRisk,
        interventionRisk: row.interventionRisk,
        untreatedRisk: shared.untreatedRisk,
        alpha: shared.alpha,
        nSimulations: shared.nSimulations,
        randomSeed: shared.randomSeed,
      }),
    })),
  };
}

export interface MappedSubgroupErrors {
  // Row index -> field -> message, for aria-invalid highlighting per subgroup row.
  rows: Record<number, Partial<Record<keyof SubgroupRowForm, string>>>;
  general: ApiError[];
}

const SUBGROUP_TRIAL_PATH_TO_FIELD: [string, keyof SubgroupRowForm][] = [
  ["arms.control.event_probability", "controlRisk"],
  ["arms.intervention.event_probability", "interventionRisk"],
  ["allocation", "totalN"],
  ["id", "id"],
];

export function mapSubgroupErrors(errors: ApiError[]): MappedSubgroupErrors {
  const rows: MappedSubgroupErrors["rows"] = {};
  const general: ApiError[] = [];
  for (const error of errors) {
    const match = error.path.match(/^subgroups\[(\d+)\](?:\.trial\.(.+)|\.(.+))?$/);
    if (!match) {
      general.push(error);
      continue;
    }
    const index = Number(match[1]);
    const innerPath = match[2] ?? match[3] ?? "";
    const field = SUBGROUP_TRIAL_PATH_TO_FIELD.find(([prefix]) =>
      innerPath.startsWith(prefix),
    )?.[1];
    if (field) {
      rows[index] = rows[index] ?? {};
      if (rows[index][field] === undefined) rows[index][field] = error.message;
    } else {
      general.push(error);
    }
  }
  return { rows, general };
}

// --- cluster trials (SPEC §17.5 / §14) -----------------------------------------------------------

export interface ClusterForm {
  controlClusters: number;
  interventionClusters: number;
  meanClusterSize: number;
  sizeType: "fixed" | "poisson" | "negative_binomial" | "lognormal";
  sizeSd: number | null;
  icc: number;
  controlRisk: number;
  interventionRisk: number;
  alpha: number;
  desiredPower: number;
  nSimulations: number;
  randomSeed: number | null;
}

export const DEFAULT_CLUSTER_FORM: ClusterForm = {
  controlClusters: 4,
  interventionClusters: 4,
  meanClusterSize: 100,
  sizeType: "fixed",
  sizeSd: null,
  icc: 0.01,
  controlRisk: 0.2,
  interventionRisk: 0.1,
  alpha: 0.05,
  desiredPower: 0.8,
  nSimulations: 5000,
  randomSeed: 12345,
};

export function buildClusterDefinition(form: ClusterForm): TrialDefinition {
  const distribution: Record<string, unknown> = { type: form.sizeType };
  if (form.sizeType !== "fixed" && form.sizeSd !== null) {
    distribution["sd"] = form.sizeSd;
  }
  return {
    schema_version: "icebergsim.trial.v2",
    id: "cluster_trial",
    label: "Post-only cluster randomized trial",
    mode: "cluster_post",
    n_simulations: form.nSimulations,
    random_seed: form.randomSeed,
    alpha: form.alpha,
    arms: {
      control: { label: "Control clusters", event_probability: form.controlRisk },
      intervention: { label: "Intervention clusters", event_probability: form.interventionRisk },
    },
    clusters: {
      control_clusters: form.controlClusters,
      intervention_clusters: form.interventionClusters,
      mean_cluster_size: form.meanClusterSize,
      cluster_size_distribution: distribution,
    },
    icc: form.icc,
  };
}

export interface PrePostExtras {
  baselineRisk: number;
  prePostCorrelation: number;
}

export const DEFAULT_PRE_POST: PrePostExtras = {
  baselineRisk: 0.2,
  prePostCorrelation: 0.5,
};

export function buildClusterPrePostDefinition(
  form: ClusterForm,
  extras: PrePostExtras,
): TrialDefinition {
  return {
    ...buildClusterDefinition(form),
    id: "cluster_pre_post_trial",
    label: "Pre/post cluster randomized trial",
    mode: "cluster_pre_post",
    baseline_event_probability: extras.baselineRisk,
    pre_post_correlation: extras.prePostCorrelation,
  };
}

const CLUSTER_PATH_TO_FIELD: [string, keyof ClusterForm][] = [
  ["clusters.control_clusters", "controlClusters"],
  ["clusters.intervention_clusters", "interventionClusters"],
  ["clusters.mean_cluster_size", "meanClusterSize"],
  ["clusters.cluster_size_distribution.sd", "sizeSd"],
  ["clusters.cluster_size_distribution.type", "sizeType"],
  ["arms.control.event_probability", "controlRisk"],
  ["arms.intervention.event_probability", "interventionRisk"],
  ["icc", "icc"],
  ["alpha", "alpha"],
  ["power", "desiredPower"],
  ["n_simulations", "nSimulations"],
  ["random_seed", "randomSeed"],
];

export interface MappedClusterErrors {
  fields: Partial<Record<keyof ClusterForm, string>>;
  prePost: Partial<Record<keyof PrePostExtras, string>>;
  general: ApiError[];
}

const PRE_POST_PATH_TO_FIELD: [string, keyof PrePostExtras][] = [
  ["baseline_event_probability", "baselineRisk"],
  ["pre_post_correlation", "prePostCorrelation"],
];

export function mapClusterErrors(errors: ApiError[]): MappedClusterErrors {
  const fields: MappedClusterErrors["fields"] = {};
  const prePost: MappedClusterErrors["prePost"] = {};
  const general: ApiError[] = [];
  for (const error of errors) {
    const prePostMatch = PRE_POST_PATH_TO_FIELD.find(([prefix]) =>
      error.path.startsWith(prefix),
    );
    if (prePostMatch) {
      if (prePost[prePostMatch[1]] === undefined) {
        prePost[prePostMatch[1]] = error.message;
      }
      continue;
    }
    const match = CLUSTER_PATH_TO_FIELD.find(([prefix]) => error.path.startsWith(prefix));
    if (match && fields[match[1]] === undefined) {
      fields[match[1]] = error.message;
    } else if (!match) {
      general.push(error);
    }
  }
  return { fields, prePost, general };
}
