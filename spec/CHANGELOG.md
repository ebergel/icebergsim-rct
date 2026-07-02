# CHANGELOG.md

## 2.0.0-alpha.1

Initial Phoenix specification for ICEBERGSIM v2.

Preserves:

- two-arm binary RCT simulation;
- sample-size and power simulation;
- trial imperfections: loss to follow-up, noncompliance, crossover;
- risk subgroup aggregation;
- scenario comparison;
- Peto/Pocock/O’Brien/custom stopping rules;
- cluster randomized trial ICC simulation and sample size.

Modernizes:

- explicit schemas;
- pure simulation engine;
- deterministic seeded RNG;
- language-independent tests;
- separate UI/API from statistical engine;
- Phoenix deletion/regeneration workflow.
