# ICEBERGSIM v2 Phoenix Specification

This repository is a Phoenix-style, implementation-independent specification for a new version of ICEBERGSIM: a randomized controlled clinical trial simulator for pragmatic and explanatory trial design.

The purpose of this package is not to preserve the old implementation. It is to preserve the meaning of ICEBERGSIM so that implementations can be regenerated in Python, Rust, JavaScript, R, or another language and verified against the same tests.

## Files

- `AXIOMS.md` — non-negotiable scientific, statistical, and software principles.
- `SPEC.md` — complete behavioral specification for the simulator.
- `ARCHITECTURE.md` — component structure, interfaces, invariants, and implementation boundaries.
- `tests.yaml` — language-agnostic correctness tests and property tests.
- `INSTALL.md` — Phoenix-style regeneration instructions for a target language.
- `schemas/trial.schema.json` — JSON Schema for trial definitions.
- `examples/` — canonical scenario definitions.
- `traceability/original_code_notes.md` — mapping from the historical ICEBERGSIM codebase to this spec.

## Grounding

This specification is grounded in:

1. The original ICEBERGSIM b3.5 zip archive uploaded by Eduardo Bergel.
2. The clinical epidemiology textbook passage describing the Controlled Trial Simulator as a pragmatic-trial simulator created by Eduardo Bergel and an international consortium.
3. The Medicina Clínica article identifying ICEBERGSIM-Clinical Trial Simulator, PRACTIHC, randomization.org, and its functions: sample size, power, RRR, confidence intervals, p-values, dropout, and compliance.
4. The Phoenix Principle: code is ephemeral; specification is source; tests are truth.

## Scope

ICEBERGSIM v2 is primarily a simulator for binary-outcome randomized controlled trials, including:

- Two-arm individually randomized trials.
- Pragmatic imperfections: noncompliance, crossover, losses to follow-up, differential risk among lost participants, and missed outcome ascertainment.
- Monte Carlo estimation of power, Type I error, confidence intervals, p-values, RRR, ARR, NNT, and related quantities.
- Risk subgroups.
- Multiple scenario comparison.
- Interim monitoring and stopping rules.
- Cluster randomized trials with intra-cluster correlation.
- Pre/post cluster randomized trials as an optional but specified extension.

ICEBERGSIM v2 deliberately remains transparent. Every output must be traceable to an input, a random seed, and a documented formula.
