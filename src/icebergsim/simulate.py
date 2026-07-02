"""Individual trial simulation engine (SPEC §6) and result assembly (§4.3, §9).

Pure functions: (validated trial, injected rng) -> frozen results. Simulation never mutates
the input definition; validation always happens before simulation (ARCHITECTURE §5).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from icebergsim import SPEC_VERSION
from icebergsim.analysis import AnalysisBatch, analyze_2x2_batch, summarize_batch
from icebergsim.model import (
    DerivedLossProbabilities,
    ImperfectionDefinition,
    SimulationSummary,
    TrialDefinition,
    ValidatedTrial,
    derive_loss_probabilities,
)
from icebergsim.rng import RNG_ALGORITHM, create_rng

IntArray = npt.NDArray[np.int64]

_IDEAL = ImperfectionDefinition()


@dataclass(frozen=True, slots=True)
class SimulatedTables:
    """Observed 2x2 counts per replicate, by assigned arm. Arrays are read-only."""

    control_events: IntArray
    control_observed: IntArray
    intervention_events: IntArray
    intervention_observed: IntArray


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """One simulation run with its reproducibility manifest (SPEC §4.3, AXIOMS §3)."""

    input_hash: str
    random_seed: int | None
    n_simulations: int
    rng_algorithm: str
    spec_version: str
    p_value_method: str
    tables: SimulatedTables
    arrays: AnalysisBatch
    summary: SimulationSummary
    warnings: tuple[str, ...]
    notes: tuple[str, ...] = ()


def simulate_trial(
    validated: ValidatedTrial,
    *,
    stream_name: str = "main",
    include_type_i_error: bool = False,
) -> SimulationResult:
    """Simulate and analyze a validated trial under the alternative hypothesis.

    With ``include_type_i_error``, a null copy (SPEC §9.2) is simulated on an independent
    RNG stream and its rejection rate is reported as the Type I error.
    """
    definition = validated.definition
    rng = create_rng(definition.random_seed, stream_name)
    tables = _simulate_tables(validated, rng)
    batch = analyze_2x2_batch(
        control_events=tables.control_events,
        control_observed=tables.control_observed,
        intervention_events=tables.intervention_events,
        intervention_observed=tables.intervention_observed,
        p_value_method=definition.analysis.p_value_method,
        zero_cell_correction=definition.zero_cell_correction,
    )
    summary = summarize_batch(batch, definition.alpha)
    if include_type_i_error:
        null_result = simulate_trial(
            null_validated_trial(validated), stream_name=f"{stream_name}/null"
        )
        summary = dataclasses.replace(
            summary,
            type_i_error=null_result.summary.power,
            type_i_error_mcse=null_result.summary.power_mcse,
        )
    warnings: list[str] = []
    if batch.zero_event_cell_count > 0:
        warnings.append(f"zero_event_cell_replicates:{batch.zero_event_cell_count}")
    if batch.zero_denominator_count > 0:
        warnings.append(
            f"zero_denominator_replicates:{batch.zero_denominator_count} "
            "(excluded from summaries; never counted as rejections)"
        )
    notes: tuple[str, ...] = ()
    if not (
        definition.control_imperfections == _IDEAL
        and definition.intervention_imperfections == _IDEAL
    ):
        # AXIOMS §9 / SPEC §5.4: the precedence rule must be stated in outputs.
        notes = ("crossover takes precedence over noncompliance when both occur (AXIOMS §9)",)
    return SimulationResult(
        input_hash=input_hash(definition),
        random_seed=definition.random_seed,
        n_simulations=definition.n_simulations,
        rng_algorithm=RNG_ALGORITHM,
        spec_version=SPEC_VERSION,
        p_value_method=definition.analysis.p_value_method,
        tables=tables,
        arrays=batch,
        summary=summary,
        warnings=tuple(warnings),
        notes=notes,
    )


def null_validated_trial(validated: ValidatedTrial) -> ValidatedTrial:
    """Null copy per SPEC §9.2: intervention event rate set to control, nuisance unchanged."""
    definition = validated.definition
    null_definition = dataclasses.replace(
        definition,
        id=f"{definition.id}__null",
        intervention=dataclasses.replace(
            definition.intervention, event_probability=definition.control.event_probability
        ),
    )
    return ValidatedTrial(
        definition=null_definition,
        n_control=validated.n_control,
        n_intervention=validated.n_intervention,
    )


def input_hash(definition: TrialDefinition) -> str:
    """Deterministic SHA-256 over the canonical JSON form of the definition (AXIOMS §3)."""
    payload = json.dumps(dataclasses.asdict(definition), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _simulate_tables(validated: ValidatedTrial, rng: np.random.Generator) -> SimulatedTables:
    definition = validated.definition
    if (
        definition.control_imperfections == _IDEAL
        and definition.intervention_imperfections == _IDEAL
    ):
        return _simulate_ideal_tables(validated, rng)
    return _simulate_imperfect_tables(validated, rng)


def _simulate_imperfect_tables(
    validated: ValidatedTrial, rng: np.random.Generator
) -> SimulatedTables:
    """SPEC §6.2 for both assigned arms; analysis stays by assigned arm (ITT)."""
    definition = validated.definition
    include_lost = definition.analysis.include_lost_in_denominator
    n_sims = definition.n_simulations
    p_control = definition.control.event_probability
    p_intervention = definition.intervention.event_probability
    p_untreated = definition.untreated_event_probability
    control_events, control_observed = simulate_arm_counts(
        n=validated.n_control,
        imperfections=definition.control_imperfections,
        p_assigned=p_control,
        p_other=p_intervention,
        p_untreated=p_untreated,
        include_lost=include_lost,
        n_sims=n_sims,
        rng=rng,
    )
    intervention_events, intervention_observed = simulate_arm_counts(
        n=validated.n_intervention,
        imperfections=definition.intervention_imperfections,
        p_assigned=p_intervention,
        p_other=p_control,
        p_untreated=p_untreated,
        include_lost=include_lost,
        n_sims=n_sims,
        rng=rng,
    )
    return SimulatedTables(
        control_events=_frozen(control_events),
        control_observed=_frozen(control_observed),
        intervention_events=_frozen(intervention_events),
        intervention_observed=_frozen(intervention_observed),
    )


def simulate_arm_counts(
    *,
    n: int,
    imperfections: ImperfectionDefinition,
    p_assigned: float,
    p_other: float,
    p_untreated: float,
    include_lost: bool,
    n_sims: int,
    rng: np.random.Generator,
) -> tuple[IntArray, IntArray]:
    """One assigned arm per SPEC §6.2, via exact multinomial/binomial vectorization (§6.3).

    Participants are independent and exchangeable, so the per-participant model factorizes
    exactly: the count in each (behavior x lost) cell is Multinomial over the joint cell
    probabilities, and observed events within a cell are Binomial with that cell's
    observed-event probability

        p_observed = p_latent * ascertainment_event + (1 - p_latent) * false_positive

    where p_latent is the derived lost/non-lost probability (AXIOMS §8) of the cell's
    actual exposure. Behavior cells encode AXIOMS §9 exactly: crossover has probability
    X and takes precedence, noncompliance-without-crossover has probability (1-X)*N,
    compliance has probability (1-X)*(1-N).
    """
    x = imperfections.crossover_probability
    noncompliance = imperfections.noncompliance_probability
    loss = imperfections.loss_probability
    # Behavior order: comply -> assigned exposure, crossover -> other arm's exposure,
    # noncompliance -> untreated exposure.
    behavior_probs = np.array(
        [(1.0 - x) * (1.0 - noncompliance), x, (1.0 - x) * noncompliance]
    )
    derived = [
        _derived_or_raise(p_exposure, imperfections)
        for p_exposure in (p_assigned, p_other, p_untreated)
    ]
    p_observed_nonlost = np.array(
        [_observed_event_probability(d.p_nonlost, imperfections) for d in derived]
    )
    p_observed_lost = np.array(
        [_observed_event_probability(d.p_lost, imperfections) for d in derived]
    )
    cell_probs = np.concatenate([behavior_probs * (1.0 - loss), behavior_probs * loss])
    cell_probs = cell_probs / cell_probs.sum()  # remove float drift; sums to 1 by design
    counts = rng.multinomial(n, cell_probs, size=n_sims)  # (n_sims, 6)
    nonlost_counts, lost_counts = counts[:, :3], counts[:, 3:]
    events = rng.binomial(nonlost_counts, p_observed_nonlost).sum(axis=1)
    if include_lost:
        events = events + rng.binomial(lost_counts, p_observed_lost).sum(axis=1)
        observed = np.full(n_sims, n, dtype=np.int64)
    else:
        observed = n - lost_counts.sum(axis=1)
    return events.astype(np.int64), observed.astype(np.int64)


def _observed_event_probability(
    p_latent: float, imperfections: ImperfectionDefinition
) -> float:
    """SPEC §6.2 step 8: ascertainment acts after latent event generation (AXIOMS §10)."""
    return (
        p_latent * imperfections.ascertainment_event_probability
        + (1.0 - p_latent)
        * imperfections.ascertainment_nonevent_false_positive_probability
    )


def _derived_or_raise(
    p_exposure: float, imperfections: ImperfectionDefinition
) -> DerivedLossProbabilities:
    result = derive_loss_probabilities(
        p_exposure, imperfections.loss_probability, imperfections.lost_event_risk_ratio
    )
    if isinstance(result, tuple):  # pragma: no cover - ValidatedTrial guarantees consistency
        raise RuntimeError(f"validated trial has inconsistent derived probabilities: {result}")
    return result


def _simulate_ideal_tables(
    validated: ValidatedTrial, rng: np.random.Generator
) -> SimulatedTables:
    """SPEC §6.1: binomial event counts per arm; everyone observed in the assigned arm."""
    definition = validated.definition
    n_sims = definition.n_simulations
    return SimulatedTables(
        control_events=_frozen(
            rng.binomial(validated.n_control, definition.control.event_probability, size=n_sims)
        ),
        control_observed=_frozen(np.full(n_sims, validated.n_control, dtype=np.int64)),
        intervention_events=_frozen(
            rng.binomial(
                validated.n_intervention,
                definition.intervention.event_probability,
                size=n_sims,
            )
        ),
        intervention_observed=_frozen(np.full(n_sims, validated.n_intervention, dtype=np.int64)),
    )


def _frozen(array: IntArray) -> IntArray:
    array.setflags(write=False)
    return array
