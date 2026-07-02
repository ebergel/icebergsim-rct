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
    ImperfectionDefinition,
    SimulationSummary,
    TrialDefinition,
    ValidatedTrial,
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
    warnings: tuple[str, ...] = ()
    if batch.zero_event_cell_count > 0:
        warnings = (f"zero_event_cell_replicates:{batch.zero_event_cell_count}",)
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
        warnings=warnings,
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
    raise NotImplementedError(
        "imperfection simulation (SPEC §6.2) is implemented in Step 5"
    )


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
