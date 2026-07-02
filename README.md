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
(`tests/test_spec_yaml.py`). Cases whose module is not yet implemented are reported as `xfail`.

## Design rules

See [CLAUDE.md](CLAUDE.md). In short: pure functions over frozen data, RNG always injected,
validation returns structured errors as data, I/O only at the edges.
