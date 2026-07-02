# INSTALL.md — Phoenix Regeneration Instructions

## 1. Requirements

- This specification package.
- A target language runtime.
- A test framework for the target language.
- An AI coding assistant or human implementer.

Recommended first implementation: Python, because numerical correctness and tests are easiest to inspect.

## 2. Generate an implementation

Copy this prompt to an AI coding assistant:

```text
Implement ICEBERGSIM v2 in [LANGUAGE].

Read these files first:
- AXIOMS.md
- SPEC.md
- ARCHITECTURE.md
- tests.yaml
- schemas/trial.schema.json
- traceability/original_code_notes.md

Create an implementation in implementations/[LANGUAGE]/.

Requirements:
1. Implement the domain models and validators.
2. Implement sample-size formulas.
3. Implement 2x2 table analysis.
4. Implement ideal and pragmatic individual binary trial simulation.
5. Implement risk subgroup aggregation.
6. Implement named stopping plans and stopping simulation.
7. Implement cluster post-only sample-size and simulation.
8. Parse tests.yaml and generate native tests.
9. Run tests until all pass.
10. Do not put statistical formulas in the UI layer.
11. All outputs must include a reproducibility manifest.

Do not preserve the historical Python 2/PyQt architecture. Preserve the behavior described in the specification.
```

## 3. Suggested Python commands

```bash
cd implementations/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 4. Deletion/regeneration

```bash
rm -rf implementations/python
# regenerate from the Phoenix specification
# run tests again
```

The project passes the Phoenix test only if the regenerated implementation passes the same tests and produces equivalent behavior on the canonical examples.

## 5. Verification checklist

- `tests.yaml` passes.
- Formula tests pass exactly within tolerance.
- Seeded simulations are reproducible.
- Stochastic simulations satisfy distributional tolerances.
- Cluster ICC behavior is present and labeled.
- Stopping rules match legacy threshold tables.
- Exported result includes seed, spec version, input hash, and analysis method.
