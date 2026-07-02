"""Multi-scenario comparison (SPEC §13).

Each scenario is a complete trial definition, validated and simulated independently on its
own RNG stream. The family result preserves scenario labels and provides an
aligned-columns summary table. It never claims that scenarios differ statistically.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from icebergsim.model import ValidationError
from icebergsim.simulate import SimulationResult, simulate_trial
from icebergsim.validate import validate_trial_definition

Errors = tuple[ValidationError, ...]

NO_COMPARISON_NOTE = (
    "scenario summaries are descriptive side-by-side results; "
    "no statistical comparison between scenarios is implied (SPEC §13)"
)


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    id: str
    label: str
    n_control: int
    n_intervention: int
    result: SimulationResult


@dataclass(frozen=True, slots=True)
class ScenarioFamilyResult:
    scenarios: tuple[ScenarioResult, ...]
    notes: tuple[str, ...]


def simulate_scenario_family(
    raw_scenarios: Sequence[Mapping[str, Any]],
) -> ScenarioFamilyResult | Errors:
    """Validate every scenario independently, then simulate each on its own stream."""
    errors: list[ValidationError] = []
    validated = []
    for index, raw in enumerate(raw_scenarios):
        result = validate_trial_definition(raw)
        if isinstance(result, tuple):
            errors.extend(
                dataclasses.replace(
                    e, path=f"scenarios[{index}]" + (f".{e.path}" if e.path else "")
                )
                for e in result
            )
        else:
            validated.append((index, result))
    if errors:
        return tuple(errors)
    if not validated:
        return (
            ValidationError(
                code="scenario_family_empty",
                message="at least one scenario is required.",
                path="scenarios",
            ),
        )
    scenarios = tuple(
        ScenarioResult(
            id=v.definition.id,
            label=v.definition.label,
            n_control=v.n_control,
            n_intervention=v.n_intervention,
            result=simulate_trial(v, stream_name=f"scenarios/{index}/{v.definition.id}"),
        )
        for index, v in validated
    )
    return ScenarioFamilyResult(scenarios=scenarios, notes=(NO_COMPARISON_NOTE,))


def scenario_summary_table(family: ScenarioFamilyResult) -> tuple[dict[str, Any], ...]:
    """Aligned-columns summary rows, one per scenario (SPEC §13), ready for CSV/JSON export."""
    return tuple(
        {
            "id": scenario.id,
            "label": scenario.label,
            "n_control": scenario.n_control,
            "n_intervention": scenario.n_intervention,
            "n_simulations": scenario.result.n_simulations,
            "power": scenario.result.summary.power,
            "power_mcse": scenario.result.summary.power_mcse,
            "mean_cer": scenario.result.summary.mean_cer,
            "mean_eer": scenario.result.summary.mean_eer,
            "mean_arr": scenario.result.summary.mean_arr,
            "mean_rr": scenario.result.summary.mean_rr,
            "mean_rrr": scenario.result.summary.mean_rrr,
            "median_arr": scenario.result.summary.median_arr,
            "ci95_arr_low": scenario.result.summary.ci95_arr_empirical[0],
            "ci95_arr_high": scenario.result.summary.ci95_arr_empirical[1],
            "mean_nnt": scenario.result.summary.mean_nnt,
            "mean_nnh": scenario.result.summary.mean_nnh,
            "type_i_error": scenario.result.summary.type_i_error,
        }
        for scenario in family.scenarios
    )
