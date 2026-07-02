"""Domain model invariants: immutability and spec defaults (SPEC §4, ARCHITECTURE §3.1)."""

from __future__ import annotations

import dataclasses

import pytest

from icebergsim.model import (
    Allocation,
    AnalysisOptions,
    ArmDefinition,
    ImperfectionDefinition,
    TrialDefinition,
)


def test_imperfection_defaults_match_spec_4_2() -> None:
    imp = ImperfectionDefinition()
    assert imp.loss_probability == 0.0
    assert imp.lost_event_risk_ratio == 1.0
    assert imp.noncompliance_probability == 0.0
    assert imp.crossover_probability == 0.0
    assert imp.ascertainment_event_probability == 1.0
    assert imp.ascertainment_nonevent_false_positive_probability == 0.0


def test_trial_definition_defaults_match_spec_4_1() -> None:
    defn = TrialDefinition(
        id="t",
        mode="individual_binary",
        n_simulations=100,
        control=ArmDefinition(event_probability=0.2),
        intervention=ArmDefinition(event_probability=0.1),
        untreated_event_probability=0.3,
    )
    assert defn.schema_version == "icebergsim.trial.v2"
    assert defn.alpha == 0.05
    assert defn.alternative == "two_sided"
    assert defn.zero_cell_correction == 0.5
    assert defn.allocation == Allocation(total_n=None, intervention_fraction=0.5)
    assert defn.analysis == AnalysisOptions(
        p_value_method="likelihood_ratio",
        confidence_interval_method="log_rr_and_wald_arr",
        include_lost_in_denominator=False,
        analysis_population="intention_to_treat_observed",
    )
    assert defn.stopping is None


def test_domain_objects_are_frozen() -> None:
    arm = ArmDefinition(event_probability=0.2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        arm.event_probability = 0.5  # type: ignore[misc]
    imp = ImperfectionDefinition()
    with pytest.raises(dataclasses.FrozenInstanceError):
        imp.loss_probability = 0.1  # type: ignore[misc]
