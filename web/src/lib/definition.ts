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
