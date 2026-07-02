# SPEC.md — ICEBERGSIM v2 Complete Behavioral Specification

## 1. Overview

ICEBERGSIM v2 is a clinical trial simulator for randomized controlled trials. It lets users define a hypothetical trial, simulate many replications of that trial, and inspect how assumptions affect estimated effect size, statistical power, Type I error, confidence intervals, p-values, and trial validity.

The historical simulator was designed to give trialists first-hand experience with “physiological statistics”: the combined effects of signal, noise, and sample size on trial interpretation. ICEBERGSIM v2 preserves that purpose while making the software regenerable from specifications and tests.

## 2. Required capabilities

### 2.1 Individually randomized two-arm binary-outcome trials

The simulator MUST support trials with:

- two assigned arms: control and intervention,
- a binary primary event,
- user-specified event probabilities in control and intervention arms,
- user-specified sample size and allocation ratio,
- Monte Carlo replication,
- analysis of each simulated 2x2 table.

### 2.2 Trial imperfections

The simulator MUST support the following imperfections independently for each assigned arm:

- loss to follow-up,
- event-risk multiplier among lost participants,
- noncompliance,
- crossover,
- incomplete outcome ascertainment,
- optional false-positive outcome ascertainment.

### 2.3 Sample-size calculation

The simulator MUST calculate conventional normal-approximation sample size for two independent proportions and, separately, simulate achieved power under specified imperfections.

### 2.4 Risk subgroup simulation

The simulator MUST support multiple risk or responsiveness subgroups. Each subgroup is a full two-arm trial scenario with its own sample size, event risks, and imperfections. The simulator MUST analyze both subgroup-specific results and the aggregate trial result obtained by summing 2x2 tables across subgroups for each simulation replicate.

### 2.5 Multi-scenario comparison

The simulator MUST support comparison of two or more trial definitions and output comparable summaries side by side.

### 2.6 Interim stopping simulation

The simulator MUST support interim looks at specified cumulative information fractions or sample fractions. It MUST implement named threshold families from the historical simulator:

- Peto-like,
- Pocock-like,
- O’Brien-Fleming-like,
- custom thresholds.

### 2.7 Cluster randomized post-only trials

The simulator MUST support post-only cluster randomized trials with:

- fixed or variable cluster sizes,
- intra-cluster correlation coefficient `ICC`,
- arm-level event probabilities,
- cluster-level event-rate generation from a beta-binomial model,
- individual-level unadjusted and cluster-adjusted analyses,
- sample-size calculation by design effect.

### 2.8 Cluster randomized pre/post trials

The simulator SHOULD support pre/post cluster randomized trials with:

- baseline and follow-up cluster observations,
- between-cluster variance implied by ICC,
- pre/post correlation,
- intervention effect on event probability,
- formula-based and simulation-based power.

This feature may be marked v2.1 if not implemented in the first implementation, but the schema and tests must reserve it.

### 2.9 Export and reproducibility

The simulator MUST export:

- input definition as JSON/YAML,
- raw simulation arrays or compressed sufficient statistics,
- summary tables as CSV and JSON,
- figures as SVG/PNG when a graphical implementation exists,
- a reproducibility manifest containing seed, version, and algorithm names.

## 3. Terminology

### 3.1 Primary event

A binary outcome of interest. Usually adverse: death, stroke, failure, hospitalization, nonresponse. Beneficial treatment usually lowers event probability.

### 3.2 CER and EER

```text
CER = control event rate = events_control / observed_control
EER = experimental event rate = events_intervention / observed_intervention
```

### 3.3 Effect measures

```text
ARR = CER - EER
RR  = EER / CER
RRR = 1 - RR
NNT = 1 / ARR, if ARR > 0
NNH = -1 / ARR, if ARR < 0
```

If denominators are zero or if `CER = 0`, outputs that require division by zero MUST be `null` with a diagnostic note unless a zero-cell correction is explicitly selected.

### 3.4 Power

Power is the proportion of simulated trials under the alternative hypothesis with `p_value < alpha`.

### 3.5 Type I error

Type I error is the proportion of simulated trials under the null hypothesis with `p_value < alpha`, where the null sets `p_intervention = p_control` while preserving nuisance assumptions unless otherwise specified.

## 4. Data model

### 4.1 TrialDefinition

A valid `TrialDefinition` object contains:

```yaml
schema_version: "icebergsim.trial.v2"
id: "string"
label: "string"
mode: "individual_binary"   # individual_binary | cluster_post | cluster_pre_post
n_simulations: integer       # recommended >= 3000 for stable teaching use
random_seed: integer | null
alpha: number                # default 0.05
alternative: "two_sided"     # two_sided | superiority_one_sided | noninferiority_one_sided
zero_cell_correction: number # default 0.5
arms:
  control:
    label: "Control"
    n: integer | null
    event_probability: number
  intervention:
    label: "Intervention"
    n: integer | null
    event_probability: number
allocation:
  total_n: integer | null
  intervention_fraction: number # default 0.5
untreated_event_probability: number
imperfections:
  control:
    loss_probability: number
    lost_event_risk_ratio: number
    noncompliance_probability: number
    crossover_probability: number
    ascertainment_event_probability: number
    ascertainment_nonevent_false_positive_probability: number
  intervention:
    loss_probability: number
    lost_event_risk_ratio: number
    noncompliance_probability: number
    crossover_probability: number
    ascertainment_event_probability: number
    ascertainment_nonevent_false_positive_probability: number
analysis:
  p_value_method: "likelihood_ratio" # likelihood_ratio | pearson_chi_square | fisher_exact | monte_carlo_exact
  confidence_interval_method: "log_rr_and_wald_arr" # default
  include_lost_in_denominator: false
  analysis_population: "intention_to_treat_observed" # see §8
stopping: null | StoppingPlan
```

If `arms.control.n` and `arms.intervention.n` are provided, they override `allocation.total_n` and `allocation.intervention_fraction`. If they are absent, compute:

```text
n_intervention = round(total_n * intervention_fraction)
n_control      = total_n - n_intervention
```

### 4.2 ImperfectionDefinition

All probabilities default to zero except ascertainment, which defaults to one for true events and zero for false-positive non-events.

```yaml
loss_probability: 0.0
lost_event_risk_ratio: 1.0
noncompliance_probability: 0.0
crossover_probability: 0.0
ascertainment_event_probability: 1.0
ascertainment_nonevent_false_positive_probability: 0.0
```

### 4.3 SimulationResult

A `SimulationResult` MUST contain:

```yaml
input_hash: string
random_seed: integer | null
n_simulations: integer
simulated_tables:
  # optional if large; otherwise store external file path
  control_events: array[number]
  control_observed: array[number]
  intervention_events: array[number]
  intervention_observed: array[number]
summary:
  mean_cer: number
  mean_eer: number
  mean_arr: number
  mean_rr: number | null
  mean_rrr: number | null
  median_arr: number
  ci95_arr_empirical: [number, number]
  ci95_rr_empirical: [number | null, number | null]
  power: number
  power_mcse: number
  type_i_error: number | null
  type_i_error_mcse: number | null
  mean_nnt: number | null
  mean_nnh: number | null
analysis_arrays:
  p_values: array[number]
  arr: array[number]
  rr: array[number | null]
  rrr: array[number | null]
warnings: array[string]
```

## 5. Validation

### 5.1 Probability constraints

Every user-specified probability MUST be in `[0, 1]`.

### 5.2 Sample-size constraints

`n_control`, `n_intervention`, and `n_simulations` MUST be positive integers. `n_simulations` SHOULD be at least 100 for exploratory UI use and at least 3000 for reported output.

### 5.3 Derived loss constraints

For each assigned arm `a` and each exposure `e` in `{control, intervention, untreated}`:

```text
p_lost(e,a) = p_exposure(e) * lost_event_risk_ratio_a
```

MUST satisfy `0 <= p_lost(e,a) <= 1`.

If `loss_probability_a > 0`, then:

```text
p_nonlost(e,a) = [p_exposure(e) - loss_probability_a * p_lost(e,a)] / [1 - loss_probability_a]
```

MUST satisfy `0 <= p_nonlost(e,a) <= 1`.

If these constraints fail, the scenario is invalid because the requested marginal event rate, loss proportion, and lost-risk multiplier are mathematically inconsistent.

### 5.4 Crossover/noncompliance constraints

For each arm:

```text
0 <= crossover_probability + noncompliance_probability <= 2
```

The sum may exceed 1 because they are modeled as independent indicators, but crossover takes precedence when both occur. Implementations MUST document this precedence.

## 6. Individual trial simulation algorithm

### 6.1 No-imperfection simulation

For each simulation `s`:

```text
events_control_s      ~ Binomial(n_control, p_control)
events_intervention_s ~ Binomial(n_intervention, p_intervention)
observed_control_s      = n_control
observed_intervention_s = n_intervention
```

Analyze each 2x2 table.

### 6.2 Imperfection simulation — default individual-level model

For each assigned arm `a`, simulation replicate `s`, and participant `i`:

1. Draw `lost_i ~ Bernoulli(loss_probability_a)`.
2. Draw `cross_i ~ Bernoulli(crossover_probability_a)`.
3. Draw `noncomp_i ~ Bernoulli(noncompliance_probability_a)`.
4. Determine actual exposure:

```text
if assigned == control:
    if cross_i: exposure = intervention
    elif noncomp_i: exposure = untreated
    else: exposure = control

if assigned == intervention:
    if cross_i: exposure = control
    elif noncomp_i: exposure = untreated
    else: exposure = intervention
```

5. Determine latent event probability:

```text
if lost_i:
    p_latent = p_lost(exposure, assigned_arm)
else:
    p_latent = p_nonlost(exposure, assigned_arm)
```

6. Draw `true_event_i ~ Bernoulli(p_latent)`.
7. If `lost_i` and `include_lost_in_denominator == false`, exclude from observed table.
8. Else ascertain observed event:

```text
if true_event_i:
    observed_event_i ~ Bernoulli(ascertainment_event_probability_a)
else:
    observed_event_i ~ Bernoulli(ascertainment_nonevent_false_positive_probability_a)
```

9. Add to assigned-arm observed denominator and assigned-arm observed event count.

The primary analysis is by assigned arm, not by actual exposure.

### 6.3 Imperfection simulation — vectorized equivalent

Implementations MAY use multinomial/binomial vectorization if it is exactly equivalent in distribution to §6.2. The equivalence must be tested by seed-invariant distributional property tests.

### 6.4 Legacy compatibility mode

The historical ICEBERGSIM code used deterministic expected subgroup sizes for combinations of crossover, noncompliance, and loss, then generated binomial events for each subgroup. ICEBERGSIM v2 MAY implement `legacy_expected_partition` mode for comparison, but the default MUST be the individual-level integer-count model in §6.2.

## 7. Analysis of a 2x2 table

Given:

```text
c = events_control
C = observed_control
e = events_intervention
E = observed_intervention
```

Non-events are:

```text
c0 = C - c
e0 = E - e
```

### 7.1 Event rates

```text
CER = c / C
EER = e / E
ARR = CER - EER
RR  = EER / CER       if CER > 0
RRR = 1 - RR          if RR is defined
```

### 7.2 NNT/NNH

```text
NNT = 1 / ARR  if ARR > 0
NNH = -1 / ARR if ARR < 0
```

If `ARR == 0`, both are null/infinite and MUST be reported as `null` with note `no_absolute_difference`.

### 7.3 Absolute risk difference confidence interval

Default Wald confidence interval:

```text
SE_ARR = sqrt(CER*(1-CER)/C + EER*(1-EER)/E)
ARR_CI = ARR ± z_(1-alpha/2) * SE_ARR
```

### 7.4 Relative risk confidence interval

If all required cells are nonzero:

```text
SE_log_RR = sqrt((1/e) - (1/E) + (1/c) - (1/C))
log_RR_CI = log(RR) ± z_(1-alpha/2) * SE_log_RR
RR_CI = exp(log_RR_CI)
RRR_CI = 1 - reverse(RR_CI)
```

If a required event count is zero, add `zero_cell_correction` to all four cells for the RR CI only, unless the correction is set to `null`, in which case the RR CI is null with warning `zero_event_cell`.

### 7.5 Likelihood-ratio p-value

For observed counts `O_j` and expected counts `E_j` under a common event rate:

```text
p_common = (c + e) / (C + E)
expected = [C*p_common, C*(1-p_common), E*p_common, E*(1-p_common)]
G = 2 * Σ O_j * ln(O_j / expected_j)
```

Terms with `O_j = 0` contribute zero. The default two-sided p-value is:

```text
p_value = 1 - CDF_chi_square(df=1, G)
```

### 7.6 Pearson chi-square p-value

```text
X2 = Σ (O_j - expected_j)^2 / expected_j
p_value = 1 - CDF_chi_square(df=1, X2)
```

### 7.7 Fisher exact p-value

Implementations SHOULD support Fisher’s exact test for small samples. If unsupported, they MUST state that it is unsupported.

## 8. Analysis populations

### 8.1 `intention_to_treat_observed`

Default. Analyze by assigned arm using observed denominators after loss to follow-up.

### 8.2 `intention_to_treat_all_randomized`

Include all randomized participants in denominators. Lost participants may be imputed as:

- event,
- non-event,
- latent simulated event,
- multiple-imputation draw.

The imputation policy MUST be explicit.

### 8.3 `as_treated`

Analyze by actual exposure. This is exploratory and MUST be labeled nonrandomized after-randomization analysis.

### 8.4 `per_protocol`

Analyze only participants who received assigned treatment and were observed. This is exploratory and MUST be labeled as vulnerable to bias.

## 9. Power and Type I error

### 9.1 Power

For `S` simulated trials under the alternative:

```text
power = count(p_value_s < alpha) / S
MCSE_power = sqrt(power * (1 - power) / S)
```

### 9.2 Type I error

To estimate Type I error, create a null copy of the trial definition:

```text
p_intervention_null = p_control
```

All nuisance parameters remain unchanged unless the user requests otherwise. Simulate and analyze as under the alternative.

```text
type_i_error = count(p_value_null_s < alpha) / S
MCSE_type_i = sqrt(type_i_error * (1 - type_i_error) / S)
```

## 10. Sample-size calculations

### 10.1 Two independent proportions, equal allocation

Inputs:

```yaml
p_control: number
p_intervention: number
alpha: number
power: number
alternative: two_sided | one_sided
```

For two-sided superiority:

```text
z_alpha = Φ^-1(1 - alpha/2)
z_beta  = Φ^-1(power)
n_per_arm = ceil( ((z_alpha + z_beta)^2 * [p_control*(1-p_control) + p_intervention*(1-p_intervention)]) / (p_control - p_intervention)^2 )
```

For one-sided superiority/noninferiority use `z_alpha = Φ^-1(1 - alpha)`.

### 10.2 Unequal allocation

For allocation ratio `r = n_intervention / n_control`, a supported approximation is:

```text
n_control = ceil( ((z_alpha + z_beta)^2 * [p_control*(1-p_control) + p_intervention*(1-p_intervention)/r]) / (p_control - p_intervention)^2 )
n_intervention = ceil(r * n_control)
```

The implementation MUST state the formula used.

## 11. Stopping rules

### 11.1 StoppingPlan

```yaml
stopping:
  enabled: true
  n_interims: integer # 1..5 in legacy named modes
  information_fractions: array[number] # increasing, values in (0,1)
  rule: "peto" # peto | pocock | obrien_fleming | custom
  interim_p_thresholds: array[number]
  final_p_threshold: number
  stop_for: "benefit_or_harm" # benefit | harm | benefit_or_harm
  minimum_total_events: integer | null
```

If information fractions are not provided, default interims are equally spaced before the final analysis:

```text
fraction_i = i / (n_interims + 1), i = 1..n_interims
```

### 11.2 Legacy named thresholds

Peto-like:

```text
interim thresholds = [0.001] repeated n_interims
final threshold = 0.05
```

Pocock-like:

```text
n_interims=1: interim=0.029, final=0.029
n_interims=2: interim=0.022, final=0.022
n_interims=3: interim=0.018, final=0.018
n_interims=4: interim=0.016, final=0.016
n_interims=5: interim=0.012, final=0.012
```

O’Brien-Fleming-like historical table:

```text
n_interims=1: interims=[0.005],                         final=0.048
n_interims=2: interims=[0.0005, 0.014],                 final=0.045
n_interims=3: interims=[0.0001, 0.004, 0.019],          final=0.043
n_interims=4: interims=[0.0001, 0.0013, 0.008, 0.023],  final=0.041
n_interims=5: interims=[0.0001, 0.0013, 0.008, 0.023, 0.027], final=0.039
```

### 11.3 Stopping simulation algorithm

For each simulation replicate:

1. Split the planned sample into cumulative looks according to information fractions.
2. Simulate incremental data for each look using the same trial model.
3. Accumulate 2x2 table.
4. Analyze accumulated table.
5. If `p_value < threshold_i` and event-count condition is satisfied, stop.
6. Record:
   - `stopped = true`,
   - `look_index`,
   - `fraction`,
   - `direction = benefit` if `ARR > 0`, else `harm` if `ARR < 0`, else `neutral`.
7. If no interim stopping occurs, simulate/analyze final data and apply final threshold.

### 11.4 Stopping outputs

The result MUST include:

```yaml
stopping_summary:
  proportion_stopped_any: number
  proportion_stopped_benefit: number
  proportion_stopped_harm: number
  proportion_stopped_by_look: array[number]
  mean_fraction_at_stop: number | null
  final_power_including_stops: number
  type_i_error_including_stops: number | null
```

## 12. Risk subgroup simulation

### 12.1 RiskSubgroupDefinition

```yaml
subgroups:
  - id: "high_risk"
    label: "High-risk patients"
    weight: number | null
    trial: TrialDefinition
  - id: "low_risk"
    label: "Low-risk patients"
    weight: number | null
    trial: TrialDefinition
```

Each subgroup trial MUST have the same `n_simulations` and random seed policy.

### 12.2 Aggregation

For each simulation replicate `s`, aggregate:

```text
control_events_total_s = Σ_k control_events_{k,s}
control_observed_total_s = Σ_k control_observed_{k,s}
intervention_events_total_s = Σ_k intervention_events_{k,s}
intervention_observed_total_s = Σ_k intervention_observed_{k,s}
```

Analyze aggregate table exactly as a standard 2x2 table. Do not average subgroup RRs to obtain the aggregate RR.

## 13. Multi-scenario comparison

A scenario family is a set of complete trial definitions. The implementation MUST:

- validate each scenario independently,
- simulate each scenario independently,
- return a scenario summary table with aligned columns,
- preserve scenario labels,
- make no claim that scenarios differ statistically unless an explicit paired-comparison simulation is performed.

## 14. Cluster randomized post-only trials

### 14.1 ClusterTrialDefinition

```yaml
mode: "cluster_post"
clusters:
  control_clusters: integer
  intervention_clusters: integer
  mean_cluster_size: number
  cluster_size_distribution:
    type: "fixed" # fixed | poisson | negative_binomial | lognormal | legacy_beta_size
    sd: number | null
    min: integer
    max: integer | null
icc: number
arms:
  control:
    event_probability: number
  intervention:
    event_probability: number
analysis:
  methods:
    - cluster_level_difference
    - adjusted_chi_square
    - unadjusted_chi_square
```

### 14.2 Design effect formula

For mean cluster size `m` and ICC `ρ`:

```text
design_effect = 1 + (m - 1) * ρ
```

Equal-arm individual sample size adjusted for clustering:

```text
n_per_arm_cluster_adjusted = n_per_arm_individual * design_effect
clusters_per_arm = ceil(n_per_arm_cluster_adjusted / m)
```

### 14.3 Beta-binomial cluster event-rate generation

For arm event probability `p` and ICC `ρ`:

```text
alpha_beta = p * (1/ρ - 1)
beta_beta  = (1-p) * (1/ρ - 1)
```

For each cluster `j`:

```text
p_cluster_j ~ Beta(alpha_beta, beta_beta)
events_j ~ Binomial(cluster_size_j, p_cluster_j)
```

If `ICC = 0`, set `p_cluster_j = p` for all clusters.

### 14.4 Cluster analyses

Minimum required analyses:

1. **Unadjusted individual chi-square**: labeled as unadjusted and potentially anti-conservative.
2. **Cluster-level difference in means**:
   - compute cluster event proportion for each cluster,
   - compare arm means using two-sample t-test or large-sample normal approximation,
   - report difference and CI.
3. **Design-effect adjusted chi-square**:
   - adjust variance or effective sample size using design effect,
   - report adjusted p-value.

## 15. Cluster pre/post trials

### 15.1 Formula

The historical pre/post cluster module used:

```text
S2_between = ICC * p_control * (1 - p_control)
S2_within  = p_control * (1 - p_control) - S2_between
n_per_arm = 4 * [S2_within + m * S2_between * (1 - corr_pre_post)] * (z_alpha + z_beta)^2 / (p_control - p_intervention)^2
clusters_per_arm = ceil(n_per_arm / m)
```

ICEBERGSIM v2 MUST preserve this formula if pre/post cluster sample size is implemented.

## 16. Visualizations

A graphical implementation SHOULD include:

1. **RR/RRR vs p-value scatter**: each point is one simulated trial.
2. **ARR distribution histogram**.
3. **Power curve over total sample size**.
4. **Confidence interval width vs sample size**.
5. **Cluster ICC sensitivity curve**.
6. **Stopping-look distribution chart**.
7. **Subgroup aggregate forest-style display**.

Visualizations MUST be generated from exported result arrays, not from separate hidden calculations.

## 17. User-facing workflows

### 17.1 Quick two-arm trial simulation

User enters total sample size, allocation fraction, control risk, intervention risk, alpha, and number of simulations. The simulator returns power, effect measures, confidence intervals, p-value distribution, and plots.

### 17.2 “What if the trial goes badly?” simulation

User adds noncompliance, crossover, loss to follow-up, and lost-risk multipliers. The simulator returns the new operating characteristics and compares them to the perfect-trial scenario.

### 17.3 Sample size and power planning

User enters control risk, intervention risk, alpha, desired power, and allocation. The simulator returns formula sample size and then runs Monte Carlo simulation to estimate achieved power under ideal and pragmatic assumptions.

### 17.4 Risk subgroup planning

User defines subgroups by baseline risk or expected responsiveness. The simulator reports how each subgroup and the combined trial affect ARR, RRR, confidence intervals, and power.

### 17.5 Cluster trial planning

User enters cluster count/size assumptions, ICC, event probabilities, and simulation count. The simulator returns cluster-adjusted sample size and simulated power under cluster correlation.

## 18. Error handling

Errors MUST be structured:

```yaml
error:
  type: "ValidationError"
  code: "derived_probability_out_of_bounds"
  message: "Derived non-lost event probability is outside [0,1]."
  path: "imperfections.control.lost_event_risk_ratio"
  details:
    assigned_arm: "control"
    exposure: "intervention"
    derived_value: -0.04
```

Warnings MUST be non-fatal and included in result output.

## 19. Performance requirements

A reference Python/NumPy implementation SHOULD satisfy:

- 10,000 individually randomized two-arm simulations with no imperfections in < 1 second on a 2024 laptop-class CPU.
- 50,000 individually randomized two-arm simulations with imperfections in < 5 seconds.
- 10,000 cluster simulations with 100 clusters per arm and mean cluster size 50 in < 10 seconds.

A pure Python implementation may be slower but must pass correctness tests.

## 20. Security and privacy

The simulator MUST NOT require patient-level identifiable data. If users import real trial data for calibration, implementations MUST treat such data as sensitive and provide local-only operation by default.

## 21. Versioning

Use semantic specification versioning:

```text
SPEC_VERSION = 2.0.0-alpha.1
```

A change that alters output definitions, formulas, or model semantics is a breaking spec change.
