// Thin fetch client. Validation failures (HTTP 422) surface as ApiValidationError carrying
// the engine's structured errors, so pages can highlight the exact offending field.

import type {
  ApiError,
  ExampleInfo,
  Meta,
  PowerCurveResponse,
  SampleSizeResponse,
  SimulationResponse,
  ClusterPrePostResponse,
  ClusterPrePostSampleSizeResponse,
  ClusterResponse,
  ClusterSampleSizeResponse,
  StoppingResponse,
  SubgroupsResponse,
  TrialDefinition,
  ValidateResponse,
} from "./types";

export class ApiValidationError extends Error {
  constructor(public readonly errors: ApiError[]) {
    super(errors.map((e) => e.message).join(" "));
    this.name = "ApiValidationError";
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (response.status === 422) {
    const body = (await response.json()) as { errors: ApiError[] };
    throw new ApiValidationError(body.errors);
  }
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${url} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function post<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  meta: (): Promise<Meta> => request("/api/meta"),
  examples: (): Promise<ExampleInfo[]> => request("/api/examples"),
  example: (name: string): Promise<TrialDefinition> => request(`/api/examples/${name}`),
  validate: (definition: TrialDefinition): Promise<ValidateResponse> =>
    post("/api/validate", definition),
  simulate: (
    definition: TrialDefinition,
    options?: { includeTypeIError?: boolean },
  ): Promise<SimulationResponse> => {
    const params = new URLSearchParams();
    if (options?.includeTypeIError) params.set("include_type_i_error", "true");
    const query = params.size > 0 ? `?${params.toString()}` : "";
    return post(`/api/simulate${query}`, definition);
  },
  sampleSizeTwoArm: (params: {
    p_control: number;
    p_intervention: number;
    alpha: number;
    power: number;
    alternative?: string;
    allocation_ratio_intervention_to_control?: number;
  }): Promise<SampleSizeResponse> => post("/api/sample-size/two-arm", params),
  powerCurve: (
    definition: TrialDefinition,
    totalSampleSizes: number[],
  ): Promise<PowerCurveResponse> =>
    post("/api/power-curve", { definition, total_sample_sizes: totalSampleSizes }),
  stopping: (
    definition: TrialDefinition,
    options?: { includeTypeIError?: boolean },
  ): Promise<StoppingResponse> => {
    const query = options?.includeTypeIError ? "?include_type_i_error=true" : "";
    return post(`/api/stopping${query}`, definition);
  },
  subgroups: (family: Record<string, unknown>): Promise<SubgroupsResponse> =>
    post("/api/subgroups", family),
  clusterSampleSize: (params: {
    p_control: number;
    p_intervention: number;
    alpha: number;
    power: number;
    mean_cluster_size: number;
    icc: number;
  }): Promise<ClusterSampleSizeResponse> => post("/api/sample-size/cluster", params),
  cluster: (definition: TrialDefinition): Promise<ClusterResponse> =>
    post("/api/cluster", definition),
  clusterPrePostSampleSize: (params: {
    p_control: number;
    p_intervention: number;
    alpha: number;
    power: number;
    mean_cluster_size: number;
    icc: number;
    pre_post_correlation: number;
  }): Promise<ClusterPrePostSampleSizeResponse> =>
    post("/api/sample-size/cluster-pre-post", params),
  clusterPrePost: (definition: TrialDefinition): Promise<ClusterPrePostResponse> =>
    post("/api/cluster-pre-post", definition),
};
