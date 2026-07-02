# ARCHITECTURE.md — ICEBERGSIM v2 Phoenix Architecture

## 1. Architecture principle

The simulator is divided into pure, testable modules. The statistical engine must not depend on the graphical interface. The interface must not contain statistical formulas. Randomness must be injectable. Every module must be replaceable by an implementation in another language that satisfies the same interface and tests.

## 2. Recommended repository layout

```text
icebergsim-v2/
├── AXIOMS.md
├── SPEC.md
├── ARCHITECTURE.md
├── tests.yaml
├── INSTALL.md
├── schemas/
│   └── trial.schema.json
├── examples/
│   ├── simple_two_arm.yaml
│   ├── pragmatic_trial_with_loss.yaml
│   ├── cluster_trial.yaml
│   └── stopping_trial.yaml
├── implementations/          # deletable
│   ├── python/
│   ├── rust/
│   └── javascript/
└── traceability/
    └── original_code_notes.md
```

## 3. Components

### 3.1 Domain model layer

Defines immutable data structures:

- `TrialDefinition`
- `ImperfectionDefinition`
- `StoppingPlan`
- `ClusterTrialDefinition`
- `RiskSubgroupDefinition`
- `SimulationResult`
- `AnalysisResult`
- `ValidationError`

All domain objects must be serializable to and from JSON/YAML.

### 3.2 Validation layer

Responsibilities:

- validate schema shape,
- validate probability bounds,
- validate derived loss/nonloss probabilities,
- validate sample sizes,
- validate stopping-plan thresholds,
- validate cluster ICC constraints,
- return all validation errors, not only the first one.

Interface:

```text
validate_trial_definition(input: object) -> ValidatedTrialDefinition | ValidationError[]
```

### 3.3 Randomness layer

Responsibilities:

- provide reproducible pseudo-random number generation,
- expose algorithm name,
- support independent streams for scenario families and subgroups,
- make seed behavior deterministic.

Interface:

```text
create_rng(seed: integer | null, stream_name: string) -> RNG
rng.binomial(n: integer, p: number, size: integer | shape) -> array
rng.bernoulli(p: number, size: integer | shape) -> array
rng.multinomial(n: integer, probs: array[number], size: integer | shape) -> array
rng.beta(alpha: number, beta: number, size: integer | shape) -> array
```

### 3.4 Individual simulation engine

Responsibilities:

- simulate ideal two-arm trials,
- simulate trial imperfections,
- return observed 2x2 table arrays,
- optionally return latent counts for diagnostics.

Interface:

```text
simulate_individual_trial(defn: TrialDefinition, rng: RNG) -> SimulatedTables
```

### 3.5 Analysis engine

Responsibilities:

- analyze one 2x2 table,
- analyze batches of 2x2 tables,
- compute effect measures,
- compute confidence intervals,
- compute p-values,
- summarize simulation arrays,
- estimate power and Type I error.

Interfaces:

```text
analyze_2x2(table: Table2x2, options: AnalysisOptions) -> AnalysisResult
analyze_2x2_batch(tables: SimulatedTables, options: AnalysisOptions) -> AnalysisBatch
summarize_analysis(batch: AnalysisBatch, alpha: number) -> SimulationSummary
```

### 3.6 Sample-size engine

Responsibilities:

- formula sample size for two independent proportions,
- allocation-adjusted sample size,
- cluster design-effect sample size,
- pre/post cluster sample size.

Interfaces:

```text
calculate_two_arm_sample_size(params: SampleSizeParams) -> SampleSizeResult
calculate_cluster_post_sample_size(params: ClusterSampleSizeParams) -> ClusterSampleSizeResult
calculate_cluster_pre_post_sample_size(params: ClusterPrePostSampleSizeParams) -> ClusterSampleSizeResult
```

### 3.7 Stopping engine

Responsibilities:

- construct named stopping plans,
- split planned sample into interim increments,
- simulate incremental data,
- apply thresholds,
- produce stopping operating characteristics.

Interfaces:

```text
make_stopping_plan(rule: string, n_interims: integer, custom: object | null) -> StoppingPlan
simulate_with_stopping(defn: TrialDefinition, rng: RNG) -> StoppingSimulationResult
```

### 3.8 Risk subgroup engine

Responsibilities:

- validate subgroup scenarios,
- simulate each subgroup,
- aggregate 2x2 tables by simulation replicate,
- analyze subgroup and aggregate outputs.

Interface:

```text
simulate_risk_subgroups(group: RiskSubgroupFamily, rng: RNG) -> RiskSubgroupResult
```

### 3.9 Cluster engine

Responsibilities:

- generate cluster sizes,
- generate cluster-specific event probabilities from ICC,
- simulate events,
- analyze with cluster-aware methods.

Interfaces:

```text
simulate_cluster_post_only(defn: ClusterTrialDefinition, rng: RNG) -> ClusterSimulationResult
simulate_cluster_pre_post(defn: ClusterPrePostTrialDefinition, rng: RNG) -> ClusterPrePostResult
```

### 3.10 Visualization layer

Responsibilities:

- consume `SimulationResult` only,
- generate plots without changing results,
- expose plot data tables as well as rendered charts.

Interfaces:

```text
make_plot_data(result: SimulationResult, plot_type: string) -> PlotData
render_plot(plot_data: PlotData, format: "svg" | "png" | "html") -> RenderedPlot
```

### 3.11 Export layer

Responsibilities:

- export inputs,
- export summary tables,
- export raw arrays when requested,
- export reproducibility manifest.

Interfaces:

```text
export_result(result: SimulationResult, format: "json" | "yaml" | "csv" | "parquet") -> bytes | file
```

### 3.12 UI/API layer

Possible front ends:

- Web application,
- desktop application,
- command-line interface,
- Python/R package API,
- REST API.

The UI must call domain services. It must not reimplement formulas.

## 4. Canonical service API

A complete implementation SHOULD expose these language-agnostic functions:

```text
validate(input) -> validation_result
sample_size_two_arm(params) -> sample_size_result
simulate_trial(input) -> simulation_result
simulate_null(input) -> simulation_result
simulate_power_curve(input, sample_sizes) -> power_curve_result
simulate_scenario_family(inputs[]) -> family_result
simulate_subgroups(subgroup_input) -> subgroup_result
simulate_cluster(input) -> cluster_result
make_stopping_plan(rule, n_interims, custom) -> stopping_plan
export_result(result, format) -> exported_artifact
```

## 5. Invariants

1. Simulation never mutates the input definition.
2. Validation occurs before simulation.
3. The same input and seed produce identical output arrays within the same implementation and RNG algorithm.
4. All probability outputs remain in `[0,1]` or are null with an explicit reason.
5. Aggregate subgroup results are computed from summed counts, not averaged effect measures.
6. Stopping-rule results are computed from cumulative data, not independent repeated full simulations at each look.
7. Cluster-adjusted analyses are labeled separately from unadjusted analyses.
8. UI labels never alter canonical statistical meaning.

## 6. Implementation notes by language

### Python

Recommended stack:

- `pydantic` or `dataclasses` for models,
- `numpy.random.Generator` for RNG,
- `scipy.stats` for chi-square, beta, normal quantiles, Fisher exact,
- `pytest` for tests,
- `matplotlib` or `plotly` for visualizations.

### Rust

Recommended stack:

- `serde` for schemas,
- `rand`/`rand_distr` for RNG,
- `statrs` for distributions,
- `proptest` for property tests.

### JavaScript/TypeScript

Recommended stack:

- TypeScript interfaces or Zod schemas,
- seeded RNG library,
- jStat or custom distribution functions,
- Vitest/Jest for tests,
- D3/Plot for visualization.

## 7. Deletion test

A project passes the ICEBERGSIM Phoenix deletion test when:

1. `implementations/` is removed.
2. A new implementation is generated from these specification files.
3. The new implementation passes `tests.yaml`.
4. Canonical examples produce statistically equivalent outputs within stated tolerances.
5. Users can perform the core workflows without behavioral regression.
