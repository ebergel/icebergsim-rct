"""Literal per-participant reference implementation of SPEC §6.2 — tests only.

This is a direct, unoptimized translation of the nine numbered steps in SPEC §6.2:
one Bernoulli indicator per participant for loss, crossover, and noncompliance;
crossover precedence; latent event from the derived lost/non-lost probability of the
actual exposure; ascertainment by assigned arm; ITT-observed table assembly.

The production engine (icebergsim.simulate) uses multinomial/binomial vectorization,
which SPEC §6.3 permits only if exactly equivalent in distribution to this model.
tests/test_imperfections.py checks that equivalence distributionally.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from icebergsim.model import DerivedLossProbabilities, ImperfectionDefinition, ValidatedTrial
from icebergsim.validate import derive_loss_probabilities

IntArray = npt.NDArray[np.int64]


def simulate_reference_arm(
    n: int,
    imperfections: ImperfectionDefinition,
    p_assigned: float,
    p_other: float,
    p_untreated: float,
    include_lost: bool,
    n_sims: int,
    rng: np.random.Generator,
) -> tuple[IntArray, IntArray]:
    """Return (observed_events, observed_denominator) arrays of shape (n_sims,)."""
    shape = (n_sims, n)
    lost = rng.random(shape) < imperfections.loss_probability
    cross = rng.random(shape) < imperfections.crossover_probability
    noncomp = rng.random(shape) < imperfections.noncompliance_probability

    # Exposure index: 0 = assigned treatment, 1 = other arm's treatment (crossover),
    # 2 = untreated (noncompliance). Crossover takes precedence (AXIOMS §9).
    exposure = np.where(cross, 1, np.where(noncomp, 2, 0))
    derived = [
        _derived(p, imperfections) for p in (p_assigned, p_other, p_untreated)
    ]
    p_lost_by_exposure = np.array([d.p_lost for d in derived])
    p_nonlost_by_exposure = np.array([d.p_nonlost for d in derived])
    p_latent = np.where(
        lost, p_lost_by_exposure[exposure], p_nonlost_by_exposure[exposure]
    )
    true_event = rng.random(shape) < p_latent
    observed_event = np.where(
        true_event,
        rng.random(shape) < imperfections.ascertainment_event_probability,
        rng.random(shape) < imperfections.ascertainment_nonevent_false_positive_probability,
    )
    included = np.ones(shape, dtype=bool) if include_lost else ~lost
    events = (observed_event & included).sum(axis=1)
    denominators = included.sum(axis=1)
    return events.astype(np.int64), denominators.astype(np.int64)


def simulate_reference_tables(
    validated: ValidatedTrial, seed: int, n_sims: int
) -> dict[str, IntArray]:
    """Simulate both assigned arms with the reference model on a plain seeded generator."""
    definition = validated.definition
    include_lost = definition.analysis.include_lost_in_denominator
    rng = np.random.default_rng(seed)
    p_control = definition.control.event_probability
    p_intervention = definition.intervention.event_probability
    p_untreated = definition.untreated_event_probability
    control_events, control_observed = simulate_reference_arm(
        validated.n_control,
        definition.control_imperfections,
        p_control,
        p_intervention,
        p_untreated,
        include_lost,
        n_sims,
        rng,
    )
    intervention_events, intervention_observed = simulate_reference_arm(
        validated.n_intervention,
        definition.intervention_imperfections,
        p_intervention,
        p_control,
        p_untreated,
        include_lost,
        n_sims,
        rng,
    )
    return {
        "control_events": control_events,
        "control_observed": control_observed,
        "intervention_events": intervention_events,
        "intervention_observed": intervention_observed,
    }


def _derived(
    p_exposure: float, imperfections: ImperfectionDefinition
) -> DerivedLossProbabilities:
    result = derive_loss_probabilities(
        p_exposure,
        imperfections.loss_probability,
        imperfections.lost_event_risk_ratio,
    )
    assert isinstance(result, DerivedLossProbabilities), result
    return result
