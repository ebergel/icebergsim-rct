# ICEBERGSIM v2 — project conventions

The Phoenix specification in `spec/` is the source of truth. `spec/tests.yaml` is canonical:
behavior is verified by tests, never by visual inspection. Do not edit files under `spec/`.

## Functional discipline (non-negotiable)

1. **Pure engine.** Every function in `src/icebergsim/` (outside `io/`) is pure:
   `(frozen inputs, rng) -> frozen outputs`. The injected `numpy.random.Generator` is the only
   permitted effect and is always an explicit parameter. No globals, no mutation of inputs.
2. **Frozen data.** Domain objects are `@dataclass(frozen=True, slots=True)`. Collections inside
   them are tuples, never lists.
3. **Validation is data, not exceptions.** `validate_*` functions return either a validated
   object or a tuple of structured `ValidationError` values (type/code/message/path/details,
   SPEC §18). All errors are collected, not just the first.
4. **No behavior classes.** Modules of small named functions. No inheritance, no mixins.
5. **I/O at the edges.** Only `icebergsim/io/` reads or writes files. The engine never touches
   the filesystem, clock, or environment.
6. **Extension by registration.** New p-value methods, stopping rules, and analysis populations
   are pure functions registered in plain dicts — adding a feature must not modify existing
   engine functions.

## Workflow

- Tests first. Each step: write tests (canonical from `spec/tests.yaml` + native unit tests),
  implement until green, then STOP and show results. Wait for explicit "go" before continuing.
- `uv` lives at `~/.local/bin/uv` (not on PATH).
- Gate every step on: `uv run pytest && uv run ruff check && uv run mypy`.

## Spec subtleties to preserve

- Crossover takes precedence over noncompliance (AXIOMS §9).
- Default simulation model is the individual-level model of SPEC §6.2; vectorized numpy is
  allowed only if exactly equivalent in distribution.
- Primary analysis is by assigned arm (ITT-observed), not actual exposure.
- Subgroup aggregation sums 2x2 counts per replicate; never average effect measures.
- Division-by-zero outputs are `null` with a diagnostic warning unless a zero-cell correction
  is explicitly selected (SPEC §3.3, §7.4).
- Every result carries a reproducibility manifest: input hash, seed, RNG algorithm name,
  spec version, analysis method.
