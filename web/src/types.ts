// TypeScript mirrors of the REST payloads (see server/icebergsim_server/routes.py and
// icebergsim/io/export.py). The UI renders these verbatim; it never computes statistics.

export interface ApiError {
  type: string;
  code: string;
  message: string;
  path: string;
  details: Record<string, unknown>;
}

export interface Manifest {
  input_hash: string;
  random_seed: number | null;
  n_simulations: number;
  rng_algorithm: string;
  spec_version: string;
  p_value_method: string;
  alpha: number;
}

export interface Summary {
  mean_cer: number | null;
  mean_eer: number | null;
  mean_arr: number | null;
  mean_rr: number | null;
  mean_rrr: number | null;
  median_arr: number | null;
  ci95_arr_empirical: [number | null, number | null];
  ci95_rr_empirical: [number | null, number | null];
  power: number;
  power_mcse: number;
  type_i_error: number | null;
  type_i_error_mcse: number | null;
  mean_nnt: number | null;
  mean_nnh: number | null;
}

export interface ScatterData {
  x: (number | null)[];
  y: (number | null)[];
  x_label: string;
  y_label: string;
  alpha: number;
}

export interface HistogramData {
  bin_edges: number[];
  counts: number[];
  n_defined: number;
  n_undefined: number;
  label: string;
}

export interface SimulationResponse {
  manifest: Manifest;
  summary: Summary;
  warnings: string[];
  notes: string[];
  plots: {
    rr_vs_p: ScatterData;
    arr_histogram: HistogramData;
  };
}

export interface ValidateResponse {
  valid: boolean;
  n_control: number;
  n_intervention: number;
}

export interface Meta {
  spec_version: string;
  rng_algorithm: string;
  p_value_methods: string[];
  analysis_populations: string[];
  stopping_rules: string[];
  export_formats: string[];
  modes: string[];
}

export interface ExampleInfo {
  name: string;
  id: string | null;
  label: string | null;
  mode: string | null;
}

// A raw trial definition, as sent to /api/validate and /api/simulate.
export type TrialDefinition = Record<string, unknown>;
