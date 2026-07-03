# Contributing to IcebergSim RCT

Thank you for considering a contribution. This project has one unusual rule that shapes
everything else:

## The specification is the source

The Phoenix specification in [`spec/`](spec/) — `AXIOMS.md`, `SPEC.md`, `ARCHITECTURE.md`,
`tests.yaml` — defines what the simulator *is*. The Python/TypeScript code is a translation.

- **Never edit files under `spec/`** in a code PR. Spec changes are their own discussion:
  a change that alters output definitions, formulas, or model semantics is a breaking
  spec change (SPEC §21) and needs an issue first.
- `spec/tests.yaml` is canonical truth. All 19 cases and 5 property tests must pass on
  every commit; the harness in `tests/test_spec_yaml.py` runs them as first-class pytest
  cases.
- If a behavior is ambiguous, the resolution order is: AXIOMS → SPEC → ARCHITECTURE →
  traceability notes → open an issue.

## Getting started

```bash
git clone https://github.com/ebergel/icebergsim-rct && cd icebergsim-rct
uv sync                                  # engine + API (Python ≥ 3.12)
cd web && npm ci && cd ..                # web UI (Node ≥ 20)
```

Run the full gate — the same one CI enforces — before pushing:

```bash
uv run pytest && uv run ruff check && uv run mypy
cd web && npx tsc --noEmit && npm test && npm run build
```

## Design rules (from [CLAUDE.md](CLAUDE.md), enforced in review)

1. **Pure engine.** Every function in `src/icebergsim/` (outside `io/`) is pure:
   `(frozen inputs, rng) -> frozen outputs`. The injected `numpy.random.Generator` is the
   only effect and always an explicit parameter. No globals, no mutation of inputs.
2. **Frozen data.** Domain objects are `@dataclass(frozen=True, slots=True)`; collections
   inside them are tuples; result arrays are set read-only.
3. **Validation is data, not exceptions.** Validators return a validated object or a tuple
   of structured `ValidationError`s (code/message/path/details) — all errors of a stage,
   not just the first. Inconsistent scenarios are rejected, never silently clipped.
4. **Extension by registration.** New p-value methods, stopping rules, plot types, and
   analysis populations are pure functions registered in plain dicts (`P_VALUE_METHODS`,
   `PLOT_TYPES`, …). Adding a feature must not modify existing engine functions.
5. **No statistics in the UI or API layer.** Routes parse, call domain services, and
   serialize. The React app renders server-provided values and plot data verbatim.
6. **Reproducibility manifests.** Every result carries input hash, seed, RNG algorithm,
   spec version, and analysis method. Same definition + same seed → identical arrays.

## Tests first, and what "tested" means here

Write the tests before the implementation. For statistical code we expect three layers
where they apply (see `tests/test_imperfections.py` for the pattern):

- **Formula pins** — recompute the spec formula independently *inside the test*.
- **Semantic pins** — degenerate scenarios where the model dictates the answer exactly.
- **Distributional checks** — means *and* variances (and joint structure where relevant)
  against a literal reference model, at more than one seed, with tolerances derived from
  Monte Carlo error — not guessed. A tolerance that cannot catch the bug the test names
  is a defect.

## Pull requests

- Keep PRs scoped to one feature or fix; include the tests that pin it.
- State any spec-interpretation decision explicitly in the PR description (the codebase
  flags these in docstrings — follow that habit).
- CI (GitHub Actions) runs the full gate on every PR; green is a hard requirement.
- Features the spec reserves (e.g. `legacy_expected_partition`, `monte_carlo_exact`)
  must keep failing with their structured "not supported" errors unless you are
  implementing them for real.

## Conduct

Be kind and assume good faith. And per AXIOMS §14: the simulator reports quantitative
consequences of assumptions — it never declares a design "valid" or "definitive", and
neither do we in docs or UI copy.
