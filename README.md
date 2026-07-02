# ICEBERGSIM v2

A clinical trial simulator for binary-outcome randomized controlled trials, regenerated from the
Phoenix specification in [spec/](spec/). The specification is the source of truth; this Python
implementation is a translation verified against [spec/tests.yaml](spec/tests.yaml).

## What it does

- Two-arm individually randomized binary-outcome trial simulation (Monte Carlo).
- Pragmatic imperfections: loss to follow-up (with lost-risk multiplier), noncompliance,
  crossover, incomplete/false-positive outcome ascertainment.
- Effect measures (ARR, RR, RRR, NNT/NNH), confidence intervals, p-values, power, Type I error.
- Formula sample size for two proportions, cluster design-effect sample size.
- Interim stopping rules (Peto, Pocock, O'Brien-Fleming, custom).
- Risk subgroup simulation with count-level aggregation.
- Post-only cluster randomized trials (beta-binomial, ICC).

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run mypy
```

Canonical spec tests are parsed from `spec/tests.yaml` and run as first-class pytest cases
(`tests/test_spec_yaml.py`).

## Status

Implements SPEC_VERSION 2.0.0-alpha.1 completely for v2.0 scope: **all 19 canonical cases
and all 5 property tests in spec/tests.yaml pass**, all four canonical examples run
end-to-end, and every result carries a reproducibility manifest (input hash, seed, PCG64,
spec version, analysis method).

Reserved for v2.1 (explicitly rejected with structured errors, never silent):
cluster pre/post *simulation* (the §15.1 sample-size formula IS implemented),
`legacy_expected_partition` mode, `monte_carlo_exact` p-values, `legacy_beta_size` cluster
sizes, non-default analysis populations (`as_treated`, `per_protocol`,
`intention_to_treat_all_randomized`), parquet export, and visualizations (SPEC §16 —
plot data can be derived from the exported result arrays).

## Design rules

See [CLAUDE.md](CLAUDE.md). In short: pure functions over frozen data, RNG always injected,
validation returns structured errors as data, I/O only at the edges.
