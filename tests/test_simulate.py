"""Ideal individual-trial simulation (SPEC §6.1), summaries and Type I error (§4.3, §9)."""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from icebergsim.simulate import (
    PowerCurveResult,
    input_hash,
    null_validated_trial,
    simulate_null,
    simulate_power_curve,
    simulate_trial,
)
from trial_builders import make_validated


def test_ideal_tables_have_correct_shapes_and_bounds() -> None:
    validated = make_validated(n_simulations=500)
    result = simulate_trial(validated)
    tables = result.tables
    for array in (
        tables.control_events,
        tables.control_observed,
        tables.intervention_events,
        tables.intervention_observed,
    ):
        assert array.shape == (500,)
    # Ideal trial: everyone is observed in the assigned arm (SPEC §6.1).
    assert np.all(tables.control_observed == validated.n_control)
    assert np.all(tables.intervention_observed == validated.n_intervention)
    assert np.all(tables.control_events >= 0)
    assert np.all(tables.control_events <= validated.n_control)
    assert np.all(tables.intervention_events <= validated.n_intervention)


def test_same_definition_reproduces_identical_arrays() -> None:
    a = simulate_trial(make_validated(random_seed=777, n_simulations=1000))
    b = simulate_trial(make_validated(random_seed=777, n_simulations=1000))
    assert np.array_equal(a.tables.control_events, b.tables.control_events)
    assert np.array_equal(a.tables.intervention_events, b.tables.intervention_events)
    assert np.array_equal(a.arrays.p_values, b.arrays.p_values)


def test_result_arrays_are_immutable() -> None:
    result = simulate_trial(make_validated(n_simulations=100))
    with pytest.raises(ValueError, match="read-only"):
        result.tables.control_events[0] = 0


def test_mean_event_rates_close_to_inputs() -> None:
    result = simulate_trial(make_validated(n_simulations=20000, random_seed=20260528))
    assert math.isclose(result.summary.mean_cer, 0.20, abs_tol=0.01)
    assert math.isclose(result.summary.mean_eer, 0.10, abs_tol=0.01)


def test_power_in_expected_range_for_canonical_trial() -> None:
    result = simulate_trial(make_validated(n_simulations=20000, random_seed=20260528))
    assert 0.75 <= result.summary.power <= 0.90


def test_power_mcse_matches_spec_9_1_formula() -> None:
    result = simulate_trial(make_validated(n_simulations=5000))
    power = result.summary.power
    assert math.isclose(
        result.summary.power_mcse, math.sqrt(power * (1 - power) / 5000), abs_tol=1e-12
    )


def test_null_copy_sets_intervention_rate_to_control_and_keeps_nuisance() -> None:
    validated = make_validated()
    null = null_validated_trial(validated)
    assert null.definition.intervention.event_probability == 0.20
    assert null.definition.control.event_probability == 0.20
    assert null.definition.untreated_event_probability == 0.30  # nuisance unchanged (§9.2)
    assert null.n_control == validated.n_control
    assert null.n_intervention == validated.n_intervention
    # The original definition is never mutated (ARCHITECTURE invariant 1).
    assert validated.definition.intervention.event_probability == 0.10


def test_type_i_error_near_alpha_when_requested() -> None:
    result = simulate_trial(
        make_validated(n_simulations=10000, random_seed=99), include_type_i_error=True
    )
    assert result.summary.type_i_error is not None
    assert result.summary.type_i_error_mcse is not None
    assert abs(result.summary.type_i_error - 0.05) < 0.02
    # Without the flag, Type I error is not computed.
    plain = simulate_trial(make_validated(n_simulations=100))
    assert plain.summary.type_i_error is None


def test_input_hash_is_deterministic_and_input_sensitive() -> None:
    a = make_validated()
    b = make_validated()
    changed = make_validated(alpha=0.01)
    assert input_hash(a.definition) == input_hash(b.definition)
    assert input_hash(a.definition) != input_hash(changed.definition)


def test_result_carries_reproducibility_manifest() -> None:
    validated = make_validated(n_simulations=100)
    result = simulate_trial(validated)
    assert result.input_hash == input_hash(validated.definition)
    assert result.random_seed == 12345
    assert result.n_simulations == 100
    assert result.rng_algorithm == "PCG64"
    assert result.spec_version == "2.0.0-alpha.1"
    assert result.p_value_method == "likelihood_ratio"


def test_summary_effect_measures_are_consistent() -> None:
    result = simulate_trial(make_validated(n_simulations=5000))
    summary = result.summary
    assert math.isclose(summary.mean_arr, summary.mean_cer - summary.mean_eer, abs_tol=1e-12)
    assert summary.ci95_arr_empirical[0] <= summary.median_arr <= summary.ci95_arr_empirical[1]
    assert summary.mean_nnt is not None and summary.mean_nnt > 0


def test_power_curve_is_monotone_and_reproducible() -> None:
    validated = make_validated(n_simulations=3000)
    curve = simulate_power_curve(validated, (100, 400, 1600))
    assert isinstance(curve, PowerCurveResult)
    assert [p.total_n for p in curve.points] == [100, 400, 1600]
    assert curve.points[1].n_control == 200 and curve.points[1].n_intervention == 200
    powers = [p.power for p in curve.points]
    for smaller, larger in zip(powers, powers[1:], strict=False):
        assert larger >= smaller - 0.03  # Monte Carlo tolerance
    again = simulate_power_curve(make_validated(n_simulations=3000), (100, 400, 1600))
    assert isinstance(again, PowerCurveResult)
    assert [p.power for p in again.points] == powers


def test_power_curve_rejects_invalid_sizes() -> None:
    result = simulate_power_curve(make_validated(n_simulations=100), (0, 400))
    assert isinstance(result, tuple)
    assert any(e.code == "power_curve_sizes_invalid" for e in result)


def test_simulate_null_convenience_matches_null_copy() -> None:
    result = simulate_null(make_validated(n_simulations=5000))
    assert abs(result.summary.power - 0.05) < 0.02  # rejection rate under the null


def test_simulation_does_not_mutate_definition() -> None:
    validated = make_validated(n_simulations=100)
    before = dataclasses.asdict(validated.definition)
    simulate_trial(validated)
    assert dataclasses.asdict(validated.definition) == before
