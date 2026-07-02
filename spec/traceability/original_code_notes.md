# Traceability Notes — Historical ICEBERGSIM b3.5 to ICEBERGSIM v2

These notes summarize the original uploaded `icebergs_b3.5.zip` codebase and how its behavior maps to the Phoenix specification.

## 1. Historical technology

The uploaded archive is a Python 2 / PyQt-style desktop application. It contains generated UI files (`*.ui`, `wb.py`, `we.py`, `wf.py`, `CTSmain.py`) and implementation files (`engine.py`, `wbimpl.py`, `weimpl.py`, `wfimpl.py`, `clusterLib.py`, `cluster_pre_post.py`, `stopUIimpl.py`, `singleSSizeimpl.py`).

The old code depends on a custom `eb` package (`ebStats`, `ebLib`, plotting/table helpers) that was not included in the zip. Therefore the zip is best treated as a behavioral source and historical trace, not as an immediately runnable modern implementation.

## 2. Historical help documentation

The HTML documentation describes ICEBERGSIM as a Clinical Trial Simulator for RCTs. It states that users define patient subgroups, sample size, outcome rates, effect size, lost-to-follow-up, compliance, and related assumptions; the program generates thousands of simulated trials; and outputs relative risks, relative risk reductions, confidence intervals, and p-values. It credits Eduardo Bergel and David Sackett as designers, identifies Eduardo as the main developer, and mentions PRACTIHC / EU and Fogarty support.

## 3. Original code modules

### `engine.py`

Core simulation engine.

Important functions:

- `gen_Mstd_n_T2x2`: generates arrays of 2x2 counts for control/intervention arms.
- `analysisArray`: computes effect measures and p-values across simulated tables.
- `simBin2`: runs simulation under the alternative and optionally stopping rules.
- `simBin`: also runs null simulation to estimate Type I error.
- `simsIfStop`: simulates interim stopping and records stopping frequencies.

Behavior preserved in v2:

- two-arm binary outcome simulation;
- alternative and null simulation;
- p-values and power;
- trial imperfections: loss, noncompliance, crossover;
- stopping rules.

Behavior modernized in v2:

- old deterministic expected subgroup partitions are replaced by individual-level multinomial/Bernoulli simulation by default;
- legacy mode may reproduce expected-partition behavior;
- results use explicit schemas and reproducibility manifests.

### `wbimpl.py`

Single-scenario/quick simulation UI logic.

Behavior preserved in v2:

- computes N per arm from total N and treatment allocation proportion;
- displays expected deaths/events;
- computes RR, RRR, ARR/DID, NNT;
- validates loss-risk-derived probabilities;
- compares ideal and imperfect trial simulations.

### `singleSSizeimpl.py`

Sample-size UI logic.

Behavior preserved in v2:

- formula-based sample size for two proportions;
- simulation-based power/CI inspection after sample-size calculation.

### `weimpl.py`

Comparison of up to four trial definitions.

Behavior preserved in v2:

- scenario-family comparison, generalized to any number of scenarios.

### `wfimpl.py`

Risk subgroup simulation.

Behavior preserved in v2:

- multiple risk subgroups;
- aggregate trial result created by summing simulated 2x2 tables across subgroups.

### `stopUIimpl.py`

Stopping-rule UI logic.

Behavior preserved in v2:

- Peto-like thresholds;
- Pocock-like thresholds;
- O’Brien-Fleming-like threshold table;
- custom thresholds;
- equally spaced default interim fractions.

### `clusterLib.py`

Post-only cluster randomized trial simulation and sample size.

Behavior preserved in v2:

- design-effect formula: `1 + (m - 1)ICC`;
- beta-binomial cluster event probability generation;
- fixed/variable cluster size concept;
- unadjusted and adjusted cluster analyses.

### `cluster_pre_post.py`

Pre/post cluster randomized trial simulation and sample size.

Behavior preserved in v2:

- formula using within-cluster variance, between-cluster variance, and pre/post correlation;
- pre/post cluster simulation as an optional v2.1 feature.

### `vars.cts`

Serialized UI defaults.

Important historical defaults:

- `N_sims = 5000`
- `N_all = 400`
- `PI_trat = 0.5`
- `PI_death_old = 0.2`
- `PI_death_new = 0.1`
- `PI_deathUntreated = 0.3`
- `PI_lost_old/new = 0`
- `PI_nonComp_old/new = 0`
- `PI_cross_old/new = 0`
- `RR_lost_old/new = 1`
- `N_addIfCero = 0.5`

These are reflected in examples and default values where clinically sensible.

## 4. Conceptual mapping

| Historical concept | v2 name |
|---|---|
| `PI_death_old` | `p_control` |
| `PI_death_new` | `p_intervention` |
| `PI_deathUntreated` | `p_untreated` |
| `PI_lost_old/new` | `loss_probability` by assigned arm |
| `RR_lost_old/new` | `lost_event_risk_ratio` by assigned arm |
| `PI_nonComp_old/new` | `noncompliance_probability` by assigned arm |
| `PI_cross_old/new` | `crossover_probability` by assigned arm |
| `N_sims` | `n_simulations` |
| `N_addIfCero` | `zero_cell_correction` |
| `A_pvalLRT` | `analysis_arrays.p_values` |
| `P_power` | `summary.power` |
| cluster ICC | `icc` |

## 5. Modernization decisions

1. **Python 2/PyQt is not preserved.** UI should be web/API/CLI or modern desktop.
2. **Simulation engine is pure.** No UI widgets or global UI dictionaries inside core statistics.
3. **RNG is explicit.** Seeds and algorithms are recorded.
4. **Schemas are explicit.** Trial definitions are portable and inspectable.
5. **Tests are canonical.** Behavior is verified by `tests.yaml`, not by visual inspection.
6. **Legacy modes are optional.** The new default prioritizes statistically coherent individual-level simulation.
