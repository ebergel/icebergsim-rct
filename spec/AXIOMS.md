# AXIOMS.md — ICEBERGSIM v2

## 0. Phoenix axiom

The specification is the source. Implementations are translations. Any implementation that passes the shared tests and satisfies this specification is a valid ICEBERGSIM v2 implementation. Any implementation that fails the tests or violates these axioms is wrong, even if it appears plausible.

## 1. Scientific purpose axiom

ICEBERGSIM is a trial-design laboratory. It does not predict the future of a specific clinical trial. It lets trialists examine how assumptions about risk, responsiveness, sample size, noncompliance, crossover, losses to follow-up, ascertainment, clustering, and stopping rules affect power, Type I error, validity, precision, and interpretability.

## 2. Pragmatic-trial axiom

The simulator must explicitly model the conditions that distinguish ideal explanatory trials from pragmatic real-world trials. Compliance, crossover, dropout, loss to follow-up, event ascertainment, and patient risk heterogeneity are not afterthoughts. They are first-class model parameters.

## 3. Transparency axiom

No output may depend on hidden state. Every result must be reproducible from:

- the full input definition,
- the software version/spec version,
- the random seed,
- the random generator algorithm name,
- and the analysis method.

## 4. Probability-bound axiom

All probabilities must lie in `[0, 1]`. Derived probabilities must also lie in `[0, 1]`. If a derived probability falls outside this range, the implementation must reject the scenario and report the exact constraint violation instead of silently clipping, unless the scenario explicitly requests a documented clipping policy.

## 5. Arm-label axiom

The simulator uses two canonical treatment arms:

- `control` / `old` / `standard`
- `intervention` / `new` / `experimental`

User-facing labels may vary, but internal output must preserve canonical arm identities.

## 6. Event-rate axiom

For a binary outcome:

- `p_control` is the probability of the primary event under control treatment.
- `p_intervention` is the probability of the primary event under intervention treatment.
- `p_untreated` is the probability of the primary event when a participant receives neither effective assigned treatment because of noncompliance.

When the outcome is adverse, a beneficial treatment is generally represented by `p_intervention < p_control`.

## 7. Estimand axiom

ICEBERGSIM v2 must report, at minimum:

- observed event rates by assigned arm,
- absolute risk reduction `ARR = CER - EER`,
- relative risk `RR = EER / CER`,
- relative risk reduction `RRR = 1 - RR`,
- number needed to treat `NNT = 1 / ARR` when `ARR > 0`,
- number needed to harm `NNH = -1 / ARR` when `ARR < 0`,
- confidence intervals,
- p-values,
- power under the alternative,
- Type I error under the null when requested.

## 8. Lost-to-follow-up axiom

Lost participants may have different true event risk from non-lost participants. If lost participants are excluded from observed denominators, the simulator must still model their latent event probability so that users can study how loss affects validity.

For assigned arm `a` and actual exposure `e`:

```text
p_lost(e, a)    = p_exposure(e) * RR_lost_a
p_nonlost(e,a) = [p_exposure(e) - L_a * p_lost(e,a)] / [1 - L_a]
```

where `L_a` is the probability of loss in assigned arm `a`. This formula preserves the marginal event probability `p_exposure(e)` across lost and non-lost participants, if all were observed. It is valid only when `L_a < 1` and both derived probabilities lie in `[0, 1]`.

## 9. Noncompliance and crossover axiom

Assigned treatment, actual received treatment, and observed follow-up status are distinct.

For participants assigned to control:

- if crossover occurs, actual exposure is intervention;
- else if noncompliance occurs, actual exposure is untreated;
- else actual exposure is control.

For participants assigned to intervention:

- if crossover occurs, actual exposure is control;
- else if noncompliance occurs, actual exposure is untreated;
- else actual exposure is intervention.

If both crossover and noncompliance indicators are true, crossover takes precedence. This matches the historical ICEBERGSIM interpretation and must be stated in outputs.

## 10. Event ascertainment axiom

Outcome ascertainment may be incomplete. If modeled, ascertainment must act after latent event generation. A true event is observed with probability `ascertainment_event`; a true non-event may be incorrectly observed as an event only if a false-positive ascertainment parameter is explicitly specified.

## 11. Cluster axiom

In cluster randomized trials, participants within the same cluster are correlated. The simulator must not analyze cluster-correlated observations as if they were independent without labeling that analysis as unadjusted. Cluster-adjusted and cluster-level analyses must be available.

## 12. Monte Carlo axiom

Monte Carlo results are estimates. The simulator must report `n_simulations` and, when practical, Monte Carlo standard error for key quantities such as power.

For estimated power `p_hat` from `S` simulations:

```text
MCSE(power) = sqrt(p_hat * (1 - p_hat) / S)
```

## 13. Stopping-rule axiom

A simulated interim stopping rule changes the operating characteristics of the trial. ICEBERGSIM v2 must report the proportion stopped, the look at which stopping occurred, whether stopping favored benefit or harm, and the final Type I error under null simulation when requested.

## 14. Output humility axiom

The simulator must never label a simulated trial design as “valid,” “ethical,” “definitive,” or “regulatory-ready.” It may report quantitative consequences of assumptions. The judgment belongs to trialists, statisticians, ethics committees, participants, and regulators.

## 15. Phoenix deletion axiom

The implementation directory must be deletable. The project is Phoenix-compliant only if a competent implementation can be regenerated from `AXIOMS.md`, `SPEC.md`, `ARCHITECTURE.md`, `tests.yaml`, and `INSTALL.md`, then pass the tests without consulting the deleted code.
