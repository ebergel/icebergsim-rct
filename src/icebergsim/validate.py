"""Validation for trial definitions (SPEC §5, §18) and derived loss probabilities (AXIOMS §8).

Validation is data, not exceptions: every function returns either a validated object or a
tuple of structured ``ValidationError`` values. Errors are collected in stages — structural
shape, then probability bounds, then derived probabilities — and all errors of the failing
stage are returned together, without noise from downstream checks that assume valid inputs.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, cast

from icebergsim.model import (
    Allocation,
    AnalysisOptions,
    AnalysisPopulation,
    ArmDefinition,
    ImperfectionDefinition,
    PValueMethod,
    StoppingPlan,
    TrialDefinition,
    ValidatedTrial,
    ValidationError,
    derive_loss_probabilities,
    round_half_up,
)
from icebergsim.model import (
    validation_error as _error,
)
from icebergsim.stopping import make_stopping_plan

__all__ = ["derive_loss_probabilities", "validate_trial_definition"]

Errors = tuple[ValidationError, ...]

MODES = ("individual_binary", "cluster_post", "cluster_pre_post")
ALTERNATIVES = ("two_sided", "superiority_one_sided", "noninferiority_one_sided")

P_VALUE_METHOD_ENUM = (
    "likelihood_ratio",
    "pearson_chi_square",
    "fisher_exact",
    "monte_carlo_exact",
)
SUPPORTED_P_VALUE_METHODS = ("likelihood_ratio", "pearson_chi_square", "fisher_exact")
ANALYSIS_POPULATION_ENUM = (
    "intention_to_treat_observed",
    "intention_to_treat_all_randomized",
    "as_treated",
    "per_protocol",
)
SUPPORTED_ANALYSIS_POPULATIONS = ("intention_to_treat_observed",)

_IMPERFECTION_DEFAULTS = ImperfectionDefinition()
_IMPERFECTION_PROBABILITY_FIELDS = (
    "loss_probability",
    "noncompliance_probability",
    "crossover_probability",
    "ascertainment_event_probability",
    "ascertainment_nonevent_false_positive_probability",
)


def validate_trial_definition(raw: Mapping[str, Any]) -> ValidatedTrial | Errors:
    """Validate a raw trial mapping into a ``ValidatedTrial`` or all errors of a stage."""
    errors: list[ValidationError] = []
    definition = _parse_definition(raw, errors)
    if errors or definition is None:
        return tuple(errors)
    _check_bounds(definition, errors)
    if errors:
        return tuple(errors)
    sizes = _resolve_sample_sizes(definition, errors)
    _check_derived_probabilities(definition, errors)
    if errors or sizes is None:
        return tuple(errors)
    n_control, n_intervention = sizes
    return ValidatedTrial(
        definition=definition, n_control=n_control, n_intervention=n_intervention
    )


# --- stage 1: structural parse --------------------------------------------------------------


def _parse_definition(
    raw: Mapping[str, Any], errors: list[ValidationError]
) -> TrialDefinition | None:
    if not isinstance(raw, Mapping):
        errors.append(_error("invalid_type", "Trial definition must be a mapping.", ""))
        return None

    mode = raw.get("mode")
    if mode not in MODES:
        errors.append(
            _error("invalid_mode", f"mode must be one of {MODES}, got {mode!r}.", "mode")
        )
    alternative = raw.get("alternative", "two_sided")
    if alternative not in ALTERNATIVES:
        errors.append(
            _error(
                "invalid_alternative",
                f"alternative must be one of {ALTERNATIVES}, got {alternative!r}.",
                "alternative",
            )
        )

    raw_imperfections = raw.get("imperfections") or {}
    if not isinstance(raw_imperfections, Mapping):
        errors.append(
            _error("invalid_type", "imperfections must be a mapping.", "imperfections")
        )
        raw_imperfections = {}
    return TrialDefinition(
        id=str(raw.get("id", "")),
        label=str(raw.get("label", raw.get("id", ""))),
        mode=mode if mode in MODES else "individual_binary",
        n_simulations=_read_int(raw, "n_simulations", None, "n_simulations", errors) or 0,
        random_seed=_read_int(raw, "random_seed", None, "random_seed", errors, optional=True),
        alpha=_read_number(raw, "alpha", 0.05, "alpha", errors),
        alternative=alternative if alternative in ALTERNATIVES else "two_sided",
        zero_cell_correction=_read_zero_cell_correction(raw, errors),
        control=_parse_arm(raw.get("arms"), "control", errors),
        intervention=_parse_arm(raw.get("arms"), "intervention", errors),
        allocation=_parse_allocation(raw.get("allocation"), errors),
        untreated_event_probability=_read_number(
            raw, "untreated_event_probability", None, "untreated_event_probability", errors
        ),
        control_imperfections=_parse_imperfections(
            raw_imperfections.get("control"), "control", errors
        ),
        intervention_imperfections=_parse_imperfections(
            raw_imperfections.get("intervention"), "intervention", errors
        ),
        analysis=_parse_analysis_options(raw.get("analysis"), errors),
        stopping=_parse_stopping(raw.get("stopping"), errors),
    )


def _parse_stopping(raw_stopping: Any, errors: list[ValidationError]) -> StoppingPlan | None:
    """Parse a SPEC §11.1 stopping block via make_stopping_plan; disabled -> None."""
    if raw_stopping is None:
        return None
    if not isinstance(raw_stopping, Mapping):
        errors.append(_error("invalid_type", "stopping must be a mapping.", "stopping"))
        return None
    if not _read_bool(raw_stopping, "enabled", default=True, path="stopping.enabled",
                      errors=errors):
        return None
    rule = raw_stopping.get("rule")
    n_interims = _read_int(raw_stopping, "n_interims", None, "stopping.n_interims", errors)
    if not isinstance(rule, str) or n_interims is None:
        if not isinstance(rule, str):
            errors.append(_error("missing_field", "stopping.rule is required.", "stopping.rule"))
        return None
    result = make_stopping_plan(
        rule,
        n_interims,
        information_fractions=_read_number_tuple(
            raw_stopping, "information_fractions", "stopping.information_fractions", errors
        ),
        interim_p_thresholds=_read_number_tuple(
            raw_stopping, "interim_p_thresholds", "stopping.interim_p_thresholds", errors
        ),
        final_p_threshold=raw_stopping.get("final_p_threshold"),
        stop_for=raw_stopping.get("stop_for", "benefit_or_harm"),
        minimum_total_events=_read_int(
            raw_stopping,
            "minimum_total_events",
            None,
            "stopping.minimum_total_events",
            errors,
            optional=True,
        ),
    )
    if isinstance(result, tuple):
        errors.extend(result)
        return None
    return result


def _read_number_tuple(
    raw: Mapping[str, Any], key: str, path: str, errors: list[ValidationError]
) -> tuple[float, ...] | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, list | tuple):
        errors.append(_error("invalid_type", f"{path} must be a list of numbers.", path))
        return None
    numbers: list[float] = []
    for i, item in enumerate(value):
        if not _is_number(item):
            errors.append(
                _error("invalid_type", f"{path}[{i}] must be a number, got {item!r}.", path)
            )
            return None
        numbers.append(float(item))
    return tuple(numbers)


def _parse_arm(raw_arms: Any, arm: str, errors: list[ValidationError]) -> ArmDefinition:
    path = f"arms.{arm}"
    raw_arm = raw_arms.get(arm) if isinstance(raw_arms, Mapping) else None
    if not isinstance(raw_arm, Mapping):
        errors.append(_error("missing_field", f"{path} is required.", path))
        return ArmDefinition(event_probability=0.0, label=arm)
    return ArmDefinition(
        event_probability=_read_number(
            raw_arm, "event_probability", None, f"{path}.event_probability", errors
        ),
        label=str(raw_arm.get("label", arm)),
        n=_read_int(raw_arm, "n", None, f"{path}.n", errors, optional=True),
    )


def _parse_allocation(raw_allocation: Any, errors: list[ValidationError]) -> Allocation:
    if raw_allocation is None:
        return Allocation()
    if not isinstance(raw_allocation, Mapping):
        errors.append(_error("invalid_type", "allocation must be a mapping.", "allocation"))
        return Allocation()
    return Allocation(
        total_n=_read_int(
            raw_allocation, "total_n", None, "allocation.total_n", errors, optional=True
        ),
        intervention_fraction=_read_number(
            raw_allocation,
            "intervention_fraction",
            0.5,
            "allocation.intervention_fraction",
            errors,
        ),
    )


def _parse_imperfections(
    raw_imp: Any, arm: str, errors: list[ValidationError]
) -> ImperfectionDefinition:
    path = f"imperfections.{arm}"
    if raw_imp is None:
        return ImperfectionDefinition()
    if not isinstance(raw_imp, Mapping):
        errors.append(_error("invalid_type", f"{path} must be a mapping.", path))
        return ImperfectionDefinition()
    values = {
        f.name: _read_number(
            raw_imp, f.name, getattr(_IMPERFECTION_DEFAULTS, f.name), f"{path}.{f.name}", errors
        )
        for f in dataclasses.fields(ImperfectionDefinition)
    }
    return ImperfectionDefinition(**values)


def _parse_analysis_options(
    raw_analysis: Any, errors: list[ValidationError]
) -> AnalysisOptions:
    """Parse SPEC §4.1 analysis options; unsupported choices are rejected, never silent."""
    if raw_analysis is None:
        return AnalysisOptions()
    if not isinstance(raw_analysis, Mapping):
        errors.append(_error("invalid_type", "analysis must be a mapping.", "analysis"))
        return AnalysisOptions()

    method = raw_analysis.get("p_value_method", "likelihood_ratio")
    if method not in P_VALUE_METHOD_ENUM:
        errors.append(
            _error(
                "invalid_p_value_method",
                f"p_value_method must be one of {P_VALUE_METHOD_ENUM}, got {method!r}.",
                "analysis.p_value_method",
            )
        )
        method = "likelihood_ratio"
    elif method not in SUPPORTED_P_VALUE_METHODS:
        errors.append(
            _error(
                "p_value_method_not_supported",
                f"p_value_method {method!r} is not supported by this implementation; "
                f"supported: {SUPPORTED_P_VALUE_METHODS}.",
                "analysis.p_value_method",
            )
        )
        method = "likelihood_ratio"

    population = raw_analysis.get("analysis_population", "intention_to_treat_observed")
    if population not in ANALYSIS_POPULATION_ENUM:
        errors.append(
            _error(
                "invalid_analysis_population",
                f"analysis_population must be one of {ANALYSIS_POPULATION_ENUM}, "
                f"got {population!r}.",
                "analysis.analysis_population",
            )
        )
        population = "intention_to_treat_observed"
    elif population not in SUPPORTED_ANALYSIS_POPULATIONS:
        errors.append(
            _error(
                "analysis_population_not_supported",
                f"analysis_population {population!r} is not supported yet; "
                f"supported: {SUPPORTED_ANALYSIS_POPULATIONS}.",
                "analysis.analysis_population",
            )
        )
        population = "intention_to_treat_observed"

    ci_method = raw_analysis.get("confidence_interval_method", "log_rr_and_wald_arr")
    if ci_method != "log_rr_and_wald_arr":
        errors.append(
            _error(
                "confidence_interval_method_not_supported",
                f"confidence_interval_method {ci_method!r} is not supported; "
                "supported: ('log_rr_and_wald_arr',).",
                "analysis.confidence_interval_method",
            )
        )
        ci_method = "log_rr_and_wald_arr"

    return AnalysisOptions(
        p_value_method=cast("PValueMethod", method),
        confidence_interval_method=str(ci_method),
        include_lost_in_denominator=_read_bool(
            raw_analysis,
            "include_lost_in_denominator",
            default=False,
            path="analysis.include_lost_in_denominator",
            errors=errors,
        ),
        analysis_population=cast("AnalysisPopulation", population),
    )


def _read_zero_cell_correction(
    raw: Mapping[str, Any], errors: list[ValidationError]
) -> float | None:
    if "zero_cell_correction" in raw and raw["zero_cell_correction"] is None:
        return None  # explicitly disabled (SPEC §7.4)
    return _read_number(raw, "zero_cell_correction", 0.5, "zero_cell_correction", errors)


# --- stage 2: bounds ------------------------------------------------------------------------


def _check_bounds(definition: TrialDefinition, errors: list[ValidationError]) -> None:
    probabilities = [
        (definition.control.event_probability, "arms.control.event_probability"),
        (definition.intervention.event_probability, "arms.intervention.event_probability"),
        (definition.untreated_event_probability, "untreated_event_probability"),
        (definition.allocation.intervention_fraction, "allocation.intervention_fraction"),
    ]
    for arm, imperfections in (
        ("control", definition.control_imperfections),
        ("intervention", definition.intervention_imperfections),
    ):
        probabilities.extend(
            (getattr(imperfections, name), f"imperfections.{arm}.{name}")
            for name in _IMPERFECTION_PROBABILITY_FIELDS
        )
        if imperfections.lost_event_risk_ratio < 0.0:
            errors.append(
                _error(
                    "risk_ratio_negative",
                    "lost_event_risk_ratio must be >= 0.",
                    f"imperfections.{arm}.lost_event_risk_ratio",
                )
            )
    for value, path in probabilities:
        if not 0.0 <= value <= 1.0:
            errors.append(
                _error(
                    "probability_out_of_bounds",
                    f"{path} = {value:g} is outside [0, 1].",
                    path,
                    details={"value": value},
                )
            )
    if not 0.0 < definition.alpha < 1.0:
        errors.append(
            _error("alpha_out_of_bounds", "alpha must be strictly between 0 and 1.", "alpha")
        )
    if definition.n_simulations < 1:
        errors.append(
            _error(
                "sample_size_not_positive",
                "n_simulations must be a positive integer.",
                "n_simulations",
            )
        )
    correction = definition.zero_cell_correction
    if correction is not None and correction <= 0.0:
        errors.append(
            _error(
                "zero_cell_correction_not_positive",
                "zero_cell_correction must be > 0, or null to disable the correction.",
                "zero_cell_correction",
            )
        )


# --- stage 3: resolution and derived probabilities ------------------------------------------


def _resolve_sample_sizes(
    definition: TrialDefinition, errors: list[ValidationError]
) -> tuple[int, int] | None:
    """Per-arm sizes: explicit arm n overrides allocation (SPEC §4.1)."""
    control_n, intervention_n = definition.control.n, definition.intervention.n
    if control_n is not None and intervention_n is not None:
        resolved = (control_n, intervention_n)
    elif control_n is not None or intervention_n is not None:
        errors.append(
            _error(
                "partial_arm_sample_size",
                "Provide n for both arms or neither; one-sided override is ambiguous.",
                "arms",
            )
        )
        return None
    elif definition.allocation.total_n is not None:
        total_n = definition.allocation.total_n
        n_intervention = round_half_up(total_n * definition.allocation.intervention_fraction)
        resolved = (total_n - n_intervention, n_intervention)
    else:
        errors.append(
            _error(
                "sample_size_missing",
                "Provide arms.control.n and arms.intervention.n, or allocation.total_n.",
                "allocation.total_n",
            )
        )
        return None
    if resolved[0] < 1 or resolved[1] < 1:
        errors.append(
            _error(
                "sample_size_not_positive",
                f"Resolved per-arm sizes must be positive integers, got "
                f"control={resolved[0]}, intervention={resolved[1]}.",
                "allocation",
            )
        )
        return None
    return resolved


def _check_derived_probabilities(
    definition: TrialDefinition, errors: list[ValidationError]
) -> None:
    """SPEC §5.3: check p_lost/p_nonlost for every assigned arm x exposure combination."""
    exposures = (
        ("control", definition.control.event_probability),
        ("intervention", definition.intervention.event_probability),
        ("untreated", definition.untreated_event_probability),
    )
    for arm, imperfections in (
        ("control", definition.control_imperfections),
        ("intervention", definition.intervention_imperfections),
    ):
        for exposure, p_exposure in exposures:
            result = derive_loss_probabilities(
                p_exposure,
                imperfections.loss_probability,
                imperfections.lost_event_risk_ratio,
                path=f"imperfections.{arm}.lost_event_risk_ratio",
                details={"assigned_arm": arm, "exposure": exposure},
            )
            if isinstance(result, tuple):
                errors.extend(result)


# --- helpers --------------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _read_number(
    raw: Mapping[str, Any],
    key: str,
    default: float | None,
    path: str,
    errors: list[ValidationError],
) -> float:
    value = raw.get(key, default)
    if value is None:
        errors.append(_error("missing_field", f"{path} is required.", path))
        return 0.0
    if not _is_number(value):
        errors.append(_error("invalid_type", f"{path} must be a number, got {value!r}.", path))
        return 0.0
    return float(value)


def _read_bool(
    raw: Mapping[str, Any],
    key: str,
    *,
    default: bool,
    path: str,
    errors: list[ValidationError],
) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        errors.append(_error("invalid_type", f"{path} must be a boolean, got {value!r}.", path))
        return default
    return value


def _read_int(
    raw: Mapping[str, Any],
    key: str,
    default: int | None,
    path: str,
    errors: list[ValidationError],
    *,
    optional: bool = False,
) -> int | None:
    value = raw.get(key, default)
    if value is None:
        if not optional:
            errors.append(_error("missing_field", f"{path} is required.", path))
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(_error("invalid_type", f"{path} must be an integer, got {value!r}.", path))
        return None
    return value
