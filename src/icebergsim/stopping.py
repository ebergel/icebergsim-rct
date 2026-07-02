"""Interim stopping engine (SPEC §11): named plans and cumulative-look simulation.

Stopping results are computed from cumulative data, never from independent full simulations
per look (ARCHITECTURE invariant 6). Each look simulates only the incremental participants
with the same trial model (ideal or imperfect), accumulates the 2x2 table, and applies the
look's threshold.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from icebergsim._version import SPEC_VERSION
from icebergsim.analysis import analyze_2x2_batch
from icebergsim.model import (
    StoppingPlan,
    StoppingSummary,
    ValidatedTrial,
    ValidationError,
    round_half_up,
)
from icebergsim.model import (
    validation_error as _error,
)
from icebergsim.rng import RNG_ALGORITHM, create_rng
from icebergsim.simulate import input_hash, null_validated_trial, simulate_arm_counts

Errors = tuple[ValidationError, ...]
IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

STOPPING_RULES = ("peto", "pocock", "obrien_fleming", "custom")
STOP_FOR_VALUES = ("benefit", "harm", "benefit_or_harm")

# Legacy threshold tables (SPEC §11.2), preserved verbatim.
_PETO_INTERIM, _PETO_FINAL = 0.001, 0.05
_POCOCK_THRESHOLDS = {1: 0.029, 2: 0.022, 3: 0.018, 4: 0.016, 5: 0.012}
_OBRIEN_FLEMING_TABLES: dict[int, tuple[tuple[float, ...], float]] = {
    1: ((0.005,), 0.048),
    2: ((0.0005, 0.014), 0.045),
    3: ((0.0001, 0.004, 0.019), 0.043),
    4: ((0.0001, 0.0013, 0.008, 0.023), 0.041),
    5: ((0.0001, 0.0013, 0.008, 0.023, 0.027), 0.039),
}


def make_stopping_plan(
    rule: str,
    n_interims: int,
    *,
    information_fractions: tuple[float, ...] | None = None,
    interim_p_thresholds: tuple[float, ...] | None = None,
    final_p_threshold: float | None = None,
    stop_for: str = "benefit_or_harm",
    minimum_total_events: int | None = None,
) -> StoppingPlan | Errors:
    """Construct a stopping plan from a named rule or custom thresholds (SPEC §11.1-§11.2)."""
    errors: list[ValidationError] = []
    if rule not in STOPPING_RULES:
        return (
            _error(
                "invalid_stopping_rule",
                f"rule must be one of {STOPPING_RULES}, got {rule!r}.",
                "stopping.rule",
            ),
        )
    if n_interims < 1 or (rule != "custom" and n_interims > 5):
        errors.append(
            _error(
                "stopping_interims_out_of_range",
                "n_interims must be >= 1 (and <= 5 for legacy named rules).",
                "stopping.n_interims",
            )
        )
    if rule != "custom" and (
        interim_p_thresholds is not None or final_p_threshold is not None
    ):
        errors.append(
            _error(
                "stopping_thresholds_only_for_custom",
                f"explicit thresholds are only allowed with rule 'custom', not {rule!r}.",
                "stopping.interim_p_thresholds",
            )
        )
    if stop_for not in STOP_FOR_VALUES:
        errors.append(
            _error(
                "invalid_stop_for",
                f"stop_for must be one of {STOP_FOR_VALUES}, got {stop_for!r}.",
                "stopping.stop_for",
            )
        )
    if minimum_total_events is not None and minimum_total_events < 1:
        errors.append(
            _error(
                "stopping_minimum_events_not_positive",
                "minimum_total_events must be a positive integer or null.",
                "stopping.minimum_total_events",
            )
        )
    if errors:
        return tuple(errors)

    thresholds = _resolve_thresholds(
        rule, n_interims, interim_p_thresholds, final_p_threshold, errors
    )
    fractions = _resolve_fractions(n_interims, information_fractions, errors)
    if errors or thresholds is None or fractions is None:
        return tuple(errors)
    interims, final = thresholds
    return StoppingPlan(
        rule=rule,  # type: ignore[arg-type]  # membership checked above
        n_interims=n_interims,
        information_fractions=fractions,
        interim_p_thresholds=interims,
        final_p_threshold=final,
        stop_for=stop_for,  # type: ignore[arg-type]  # membership checked above
        minimum_total_events=minimum_total_events,
    )


def _resolve_thresholds(
    rule: str,
    n_interims: int,
    interim_p_thresholds: tuple[float, ...] | None,
    final_p_threshold: float | None,
    errors: list[ValidationError],
) -> tuple[tuple[float, ...], float] | None:
    if rule == "peto":
        return (_PETO_INTERIM,) * n_interims, _PETO_FINAL
    if rule == "pocock":
        threshold = _POCOCK_THRESHOLDS[n_interims]
        return (threshold,) * n_interims, threshold
    if rule == "obrien_fleming":
        return _OBRIEN_FLEMING_TABLES[n_interims]
    return _resolve_custom_thresholds(
        n_interims, interim_p_thresholds, final_p_threshold, errors
    )


def _resolve_custom_thresholds(
    n_interims: int,
    interim_p_thresholds: tuple[float, ...] | None,
    final_p_threshold: float | None,
    errors: list[ValidationError],
) -> tuple[tuple[float, ...], float] | None:
    if interim_p_thresholds is None or final_p_threshold is None:
        errors.append(
            _error(
                "stopping_threshold_missing",
                "custom rule requires interim_p_thresholds and final_p_threshold.",
                "stopping.interim_p_thresholds",
            )
        )
        return None
    if len(interim_p_thresholds) != n_interims:
        errors.append(
            _error(
                "stopping_threshold_length_mismatch",
                f"interim_p_thresholds has length {len(interim_p_thresholds)}, "
                f"expected n_interims = {n_interims}.",
                "stopping.interim_p_thresholds",
            )
        )
        return None
    if any(not 0.0 < t < 1.0 for t in (*interim_p_thresholds, final_p_threshold)):
        errors.append(
            _error(
                "stopping_threshold_out_of_bounds",
                "all p-value thresholds must be strictly between 0 and 1.",
                "stopping.interim_p_thresholds",
            )
        )
        return None
    return tuple(interim_p_thresholds), float(final_p_threshold)


def _resolve_fractions(
    n_interims: int,
    information_fractions: tuple[float, ...] | None,
    errors: list[ValidationError],
) -> tuple[float, ...] | None:
    if information_fractions is None:
        # SPEC §11.1 default: equally spaced before the final analysis.
        return tuple(i / (n_interims + 1) for i in range(1, n_interims + 1))
    valid = (
        len(information_fractions) == n_interims
        and all(0.0 < f < 1.0 for f in information_fractions)
        and all(a < b for a, b in zip(information_fractions, information_fractions[1:],
                                      strict=False))
    )
    if not valid:
        errors.append(
            _error(
                "stopping_fractions_invalid",
                "information_fractions must have length n_interims, lie strictly in (0, 1), "
                "and be strictly increasing.",
                "stopping.information_fractions",
            )
        )
        return None
    return tuple(information_fractions)


# --- stopping simulation (SPEC §11.3-§11.4) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoppingSimulationResult:
    """Stopping simulation with per-replicate stop records and its manifest (AXIOMS §3)."""

    input_hash: str
    random_seed: int | None
    n_simulations: int
    rng_algorithm: str
    spec_version: str
    plan: StoppingPlan
    look_sample_sizes: tuple[tuple[int, int], ...]  # cumulative (control, intervention)
    summary: StoppingSummary
    stopped: BoolArray
    look_at_stop: IntArray  # 1-based interim look index; 0 = no interim stop
    direction_at_stop: IntArray  # 1 = benefit, -1 = harm, 0 = none/neutral
    fraction_at_stop: FloatArray  # NaN where not stopped


def simulate_with_stopping(
    validated: ValidatedTrial,
    *,
    stream_name: str = "stopping",
    include_type_i_error: bool = False,
) -> StoppingSimulationResult:
    """Simulate a trial with interim looks per SPEC §11.3 and summarize per §11.4."""
    definition = validated.definition
    plan = definition.stopping
    if plan is None:
        raise ValueError("trial definition has no stopping plan (stopping is null/disabled)")
    rng = create_rng(definition.random_seed, stream_name)
    n_sims = definition.n_simulations

    fractions = (*plan.information_fractions, 1.0)
    cumulative_sizes = tuple(
        (round_half_up(f * validated.n_control), round_half_up(f * validated.n_intervention))
        for f in fractions
    )

    cum_control_events = np.zeros(n_sims, dtype=np.int64)
    cum_control_observed = np.zeros(n_sims, dtype=np.int64)
    cum_intervention_events = np.zeros(n_sims, dtype=np.int64)
    cum_intervention_observed = np.zeros(n_sims, dtype=np.int64)
    stopped = np.zeros(n_sims, dtype=np.bool_)
    look_at_stop = np.zeros(n_sims, dtype=np.int64)
    direction_at_stop = np.zeros(n_sims, dtype=np.int64)
    fraction_at_stop = np.full(n_sims, np.nan, dtype=np.float64)
    rejected_final = np.zeros(n_sims, dtype=np.bool_)

    previous_control, previous_intervention = 0, 0
    for look, fraction in enumerate(fractions):
        target_control, target_intervention = cumulative_sizes[look]
        control_events, control_observed = _increment(
            validated, "control", target_control - previous_control, n_sims, rng
        )
        intervention_events, intervention_observed = _increment(
            validated, "intervention", target_intervention - previous_intervention, n_sims, rng
        )
        previous_control, previous_intervention = target_control, target_intervention
        cum_control_events += control_events
        cum_control_observed += control_observed
        cum_intervention_events += intervention_events
        cum_intervention_observed += intervention_observed

        batch = analyze_2x2_batch(
            control_events=cum_control_events,
            control_observed=cum_control_observed,
            intervention_events=cum_intervention_events,
            intervention_observed=cum_intervention_observed,
            p_value_method=definition.analysis.p_value_method,
            zero_cell_correction=definition.zero_cell_correction,
        )
        direction = np.where(batch.arr > 0.0, 1, np.where(batch.arr < 0.0, -1, 0)).astype(
            np.int64
        )
        is_final = look == len(fractions) - 1
        with np.errstate(invalid="ignore"):  # NaN p-values never cross a threshold
            crosses = batch.p_values < (
                plan.final_p_threshold if is_final else plan.interim_p_thresholds[look]
            )
        if is_final:
            rejected_final = ~stopped & crosses
            break
        allowed = _direction_allowed(plan, direction)
        if plan.minimum_total_events is not None:
            allowed = allowed & (
                cum_control_events + cum_intervention_events >= plan.minimum_total_events
            )
        newly_stopped = ~stopped & crosses & allowed
        stopped |= newly_stopped
        look_at_stop[newly_stopped] = look + 1
        direction_at_stop[newly_stopped] = direction[newly_stopped]
        fraction_at_stop[newly_stopped] = fraction

    summary = _summarize_stopping(
        plan, stopped, look_at_stop, direction_at_stop, fraction_at_stop, rejected_final
    )
    if include_type_i_error:
        null_result = simulate_with_stopping(
            null_validated_trial(validated), stream_name=f"{stream_name}/null"
        )
        summary = dataclasses.replace(
            summary,
            type_i_error_including_stops=null_result.summary.final_power_including_stops,
            type_i_error_mcse=float(
                np.sqrt(
                    null_result.summary.final_power_including_stops
                    * (1.0 - null_result.summary.final_power_including_stops)
                    / n_sims
                )
            ),
        )
    return StoppingSimulationResult(
        input_hash=input_hash(definition),
        random_seed=definition.random_seed,
        n_simulations=n_sims,
        rng_algorithm=RNG_ALGORITHM,
        spec_version=SPEC_VERSION,
        plan=plan,
        look_sample_sizes=cumulative_sizes,
        summary=summary,
        stopped=_read_only(stopped),
        look_at_stop=_read_only(look_at_stop),
        direction_at_stop=_read_only(direction_at_stop),
        fraction_at_stop=_read_only(fraction_at_stop),
    )


def _increment(
    validated: ValidatedTrial,
    arm: str,
    n_increment: int,
    n_sims: int,
    rng: np.random.Generator,
) -> tuple[IntArray, IntArray]:
    """Incremental data for one look, using the same trial model as fixed designs."""
    definition = validated.definition
    if arm == "control":
        imperfections = definition.control_imperfections
        p_assigned = definition.control.event_probability
        p_other = definition.intervention.event_probability
    else:
        imperfections = definition.intervention_imperfections
        p_assigned = definition.intervention.event_probability
        p_other = definition.control.event_probability
    return simulate_arm_counts(
        n=n_increment,
        imperfections=imperfections,
        p_assigned=p_assigned,
        p_other=p_other,
        p_untreated=definition.untreated_event_probability,
        include_lost=definition.analysis.include_lost_in_denominator,
        n_sims=n_sims,
        rng=rng,
    )


def _direction_allowed(plan: StoppingPlan, direction: IntArray) -> BoolArray:
    if plan.stop_for == "benefit":
        return np.asarray(direction == 1)
    if plan.stop_for == "harm":
        return np.asarray(direction == -1)
    return np.ones(direction.shape, dtype=np.bool_)


def _summarize_stopping(
    plan: StoppingPlan,
    stopped: BoolArray,
    look_at_stop: IntArray,
    direction_at_stop: IntArray,
    fraction_at_stop: FloatArray,
    rejected_final: BoolArray,
) -> StoppingSummary:
    n_sims = stopped.size
    fractions_of_stopped = fraction_at_stop[stopped]
    return StoppingSummary(
        proportion_stopped_any=float(stopped.mean()),
        proportion_stopped_benefit=float((stopped & (direction_at_stop == 1)).mean()),
        proportion_stopped_harm=float((stopped & (direction_at_stop == -1)).mean()),
        proportion_stopped_by_look=tuple(
            float((look_at_stop == look).sum() / n_sims)
            for look in range(1, plan.n_interims + 1)
        ),
        mean_fraction_at_stop=(
            float(fractions_of_stopped.mean()) if fractions_of_stopped.size else None
        ),
        final_power_including_stops=float((stopped | rejected_final).mean()),
    )


def _read_only[ArrayT: np.generic](array: npt.NDArray[ArrayT]) -> npt.NDArray[ArrayT]:
    array.setflags(write=False)
    return array
