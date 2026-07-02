"""Risk subgroup simulation (SPEC §12).

Each subgroup is a full two-arm trial scenario. The aggregate trial result is obtained by
summing 2x2 counts across subgroups within each simulation replicate and analyzing the
summed table exactly like a standard 2x2 table — never by averaging subgroup effect
measures (SPEC §12.2, ARCHITECTURE invariant 5).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from icebergsim._version import SPEC_VERSION
from icebergsim.analysis import AnalysisBatch, analyze_2x2_batch, summarize_batch
from icebergsim.model import (
    SimulationSummary,
    Table2x2,
    ValidatedTrial,
    ValidationError,
)
from icebergsim.model import (
    validation_error as _error,
)
from icebergsim.rng import RNG_ALGORITHM
from icebergsim.simulate import (
    SimulatedTables,
    SimulationResult,
    input_hash,
    simulate_trial,
)
from icebergsim.validate import validate_trial_definition

Errors = tuple[ValidationError, ...]


@dataclass(frozen=True, slots=True)
class ValidatedSubgroup:
    id: str
    label: str
    weight: float | None
    validated: ValidatedTrial


@dataclass(frozen=True, slots=True)
class ValidatedSubgroupFamily:
    subgroups: tuple[ValidatedSubgroup, ...]


@dataclass(frozen=True, slots=True)
class SubgroupResult:
    id: str
    label: str
    result: SimulationResult


@dataclass(frozen=True, slots=True)
class RiskSubgroupResult:
    """Per-subgroup results plus the count-aggregated trial result, with manifest."""

    input_hash: str
    random_seed: int | None
    n_simulations: int
    rng_algorithm: str
    spec_version: str
    subgroups: tuple[SubgroupResult, ...]
    aggregate_tables: SimulatedTables
    aggregate_arrays: AnalysisBatch
    aggregate_summary: SimulationSummary
    warnings: tuple[str, ...]


def aggregate_subgroup_tables(tables: Sequence[Table2x2]) -> Table2x2:
    """SPEC §12.2: aggregate by summing counts, never by averaging effect measures."""
    return Table2x2(
        control_events=sum(t.control_events for t in tables),
        control_observed=sum(t.control_observed for t in tables),
        intervention_events=sum(t.intervention_events for t in tables),
        intervention_observed=sum(t.intervention_observed for t in tables),
    )


def validate_subgroup_family(raw: Mapping[str, Any]) -> ValidatedSubgroupFamily | Errors:
    """Validate a subgroup family: each trial fully, plus SPEC §12.1 consistency rules."""
    if not isinstance(raw, Mapping) or not isinstance(raw.get("subgroups"), list):
        return (
            _error(
                "invalid_type", "subgroup family must be a mapping with a 'subgroups' list.",
                "subgroups",
            ),
        )
    raw_subgroups = raw["subgroups"]
    if not raw_subgroups:
        return (
            _error("subgroup_family_empty", "at least one subgroup is required.", "subgroups"),
        )

    errors: list[ValidationError] = []
    subgroups: list[ValidatedSubgroup] = []
    for index, raw_subgroup in enumerate(raw_subgroups):
        subgroup = _validate_subgroup(index, raw_subgroup, errors)
        if subgroup is not None:
            subgroups.append(subgroup)
    if not errors:
        _check_family_consistency(subgroups, errors)
    if errors:
        return tuple(errors)
    return ValidatedSubgroupFamily(subgroups=tuple(subgroups))


def _validate_subgroup(
    index: int, raw_subgroup: Any, errors: list[ValidationError]
) -> ValidatedSubgroup | None:
    path = f"subgroups[{index}]"
    if not isinstance(raw_subgroup, Mapping):
        errors.append(_error("invalid_type", f"{path} must be a mapping.", path))
        return None
    subgroup_id = raw_subgroup.get("id")
    if not isinstance(subgroup_id, str) or not subgroup_id:
        errors.append(_error("missing_field", f"{path}.id is required.", f"{path}.id"))
        return None
    weight = raw_subgroup.get("weight")
    if weight is not None and (
        isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0
    ):
        errors.append(
            _error(
                "subgroup_weight_invalid",
                f"{path}.weight must be a positive number or null.",
                f"{path}.weight",
            )
        )
        return None
    validated = validate_trial_definition(raw_subgroup.get("trial") or {})
    if isinstance(validated, tuple):
        errors.extend(
            dataclasses.replace(
                e, path=f"{path}.trial" + (f".{e.path}" if e.path else "")
            )
            for e in validated
        )
        return None
    return ValidatedSubgroup(
        id=subgroup_id,
        label=str(raw_subgroup.get("label", subgroup_id)),
        weight=float(weight) if weight is not None else None,
        validated=validated,
    )


def _check_family_consistency(
    subgroups: Sequence[ValidatedSubgroup], errors: list[ValidationError]
) -> None:
    """SPEC §12.1: same n_simulations and random seed policy; analysis must be aggregable."""
    ids = [s.id for s in subgroups]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(
            _error(
                "subgroup_duplicate_id", f"subgroup id {duplicate!r} appears more than once.",
                "subgroups",
            )
        )
    first = subgroups[0].validated.definition
    for subgroup in subgroups[1:]:
        definition = subgroup.validated.definition
        path = f"subgroups[{ids.index(subgroup.id)}].trial"
        if definition.n_simulations != first.n_simulations:
            errors.append(
                _error(
                    "subgroup_n_simulations_mismatch",
                    "all subgroup trials must share the same n_simulations (SPEC §12.1).",
                    f"{path}.n_simulations",
                )
            )
        if definition.random_seed != first.random_seed:
            errors.append(
                _error(
                    "subgroup_seed_mismatch",
                    "all subgroup trials must share the same random seed policy (SPEC §12.1).",
                    f"{path}.random_seed",
                )
            )
        if (
            definition.alpha != first.alpha
            or definition.analysis != first.analysis
            or definition.zero_cell_correction != first.zero_cell_correction
        ):
            errors.append(
                _error(
                    "subgroup_analysis_mismatch",
                    "all subgroup trials must share alpha, analysis options, and "
                    "zero_cell_correction so the aggregate analysis is coherent.",
                    f"{path}.analysis",
                )
            )


def simulate_risk_subgroups(family: ValidatedSubgroupFamily) -> RiskSubgroupResult:
    """Simulate every subgroup on its own RNG stream and analyze the count-aggregate."""
    results = tuple(
        SubgroupResult(
            id=subgroup.id,
            label=subgroup.label,
            result=simulate_trial(subgroup.validated, stream_name=f"subgroups/{subgroup.id}"),
        )
        for subgroup in family.subgroups
    )
    aggregate_tables = SimulatedTables(
        control_events=_summed(results, "control_events"),
        control_observed=_summed(results, "control_observed"),
        intervention_events=_summed(results, "intervention_events"),
        intervention_observed=_summed(results, "intervention_observed"),
    )
    first = family.subgroups[0].validated.definition
    aggregate_arrays = analyze_2x2_batch(
        control_events=aggregate_tables.control_events,
        control_observed=aggregate_tables.control_observed,
        intervention_events=aggregate_tables.intervention_events,
        intervention_observed=aggregate_tables.intervention_observed,
        p_value_method=first.analysis.p_value_method,
        zero_cell_correction=first.zero_cell_correction,
    )
    warnings = tuple(
        f"{subgroup.id}: {warning}" for subgroup in results for warning in subgroup.result.warnings
    )
    return RiskSubgroupResult(
        input_hash=_family_hash(family),
        random_seed=first.random_seed,
        n_simulations=first.n_simulations,
        rng_algorithm=RNG_ALGORITHM,
        spec_version=SPEC_VERSION,
        subgroups=results,
        aggregate_tables=aggregate_tables,
        aggregate_arrays=aggregate_arrays,
        aggregate_summary=summarize_batch(aggregate_arrays, first.alpha),
        warnings=warnings,
    )


def _summed(results: Sequence[SubgroupResult], field: str) -> Any:
    total = np.sum([getattr(s.result.tables, field) for s in results], axis=0)
    total.setflags(write=False)
    return total


def _family_hash(family: ValidatedSubgroupFamily) -> str:
    combined = "".join(
        f"{s.id}:{input_hash(s.validated.definition)}" for s in family.subgroups
    )
    return hashlib.sha256(combined.encode()).hexdigest()
