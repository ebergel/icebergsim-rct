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
