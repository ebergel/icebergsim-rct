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

export interface SampleSizeResponse {
  n_control: number;
  n_intervention: number;
  n_total: number;
  unrounded_n_control: number;
  unrounded_n_intervention: number;
  allocation_ratio_intervention_to_control: number;
  formula: string;
}

export interface PowerCurvePoint {
  total_n: number;
  n_control: number;
  n_intervention: number;
  power: number;
  power_mcse: number;
}

export interface PowerCurveResponse {
  input_hash: string;
  random_seed: number | null;
  rng_algorithm: string;
  spec_version: string;
  points: PowerCurvePoint[];
  plot: { total_n: number[]; power: number[]; power_mcse: number[] };
}

export interface StoppingPlanT {
  rule: string;
  n_interims: number;
  information_fractions: number[];
  interim_p_thresholds: number[];
  final_p_threshold: number;
  enabled: boolean;
  stop_for: string;
  minimum_total_events: number | null;
}

export interface StoppingSummaryT {
  proportion_stopped_any: number;
  proportion_stopped_benefit: number;
  proportion_stopped_harm: number;
  proportion_stopped_by_look: number[];
  mean_fraction_at_stop: number | null;
  final_power_including_stops: number;
  type_i_error_including_stops: number | null;
  type_i_error_mcse: number | null;
}

export interface StopByLookData {
  looks: number[];
  information_fractions: number[];
  proportions: number[];
  proportion_reaching_final: number;
}

export interface StoppingResponse {
  manifest: {
    input_hash: string;
    random_seed: number | null;
    n_simulations: number;
    rng_algorithm: string;
    spec_version: string;
  };
  plan: StoppingPlanT;
  look_sample_sizes: [number, number][];
  summary: StoppingSummaryT;
  plots: { stop_by_look: StopByLookData };
}

export interface ForestRowT {
  label: string;
  rr: number | null;
  rr_low: number | null;
  rr_high: number | null;
  arr: number | null;
  arr_low: number | null;
  arr_high: number | null;
  is_aggregate: boolean;
}

export interface SubgroupResultRow {
  id: string;
  label: string;
  n_control: number;
  n_intervention: number;
  summary: Summary;
}

export interface SubgroupsResponse {
  manifest: {
    input_hash: string;
    random_seed: number | null;
    n_simulations: number;
    rng_algorithm: string;
    spec_version: string;
  };
  subgroups: SubgroupResultRow[];
  aggregate: { summary: Summary };
  plots: { forest: { rows: ForestRowT[] } };
  warnings: string[];
  notes: string[];
}
