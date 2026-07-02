"""Stopping plans (SPEC §11.1-§11.2) and cumulative-look stopping simulation (§11.3-§11.4)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from icebergsim.model import StoppingPlan, ValidatedTrial, ValidationError
from icebergsim.simulate import simulate_trial
from icebergsim.stopping import make_stopping_plan, simulate_with_stopping
from icebergsim.validate import validate_trial_definition
from trial_builders import make_raw, make_validated

# Legacy threshold tables copied literally from SPEC §11.2 — pinning the data, not the code.
PETO_INTERIM, PETO_FINAL = 0.001, 0.05
POCOCK = {1: 0.029, 2: 0.022, 3: 0.018, 4: 0.016, 5: 0.012}
OBF = {
    1: ((0.005,), 0.048),
    2: ((0.0005, 0.014), 0.045),
    3: ((0.0001, 0.004, 0.019), 0.043),
    4: ((0.0001, 0.0013, 0.008, 0.023), 0.041),
    5: ((0.0001, 0.0013, 0.008, 0.023, 0.027), 0.039),
}


def plan_of(result: StoppingPlan | tuple[ValidationError, ...]) -> StoppingPlan:
    assert isinstance(result, StoppingPlan), f"expected plan, got {result}"
    return result


def codes_of(result: StoppingPlan | tuple[ValidationError, ...]) -> list[str]:
    assert isinstance(result, tuple), f"expected errors, got {result}"
    return [e.code for e in result]


# --- named plans (SPEC §11.2) ----------------------------------------------------------------


@pytest.mark.parametrize("n_interims", [1, 2, 3, 4, 5])
def test_peto_plan_matches_legacy_table(n_interims: int) -> None:
    plan = plan_of(make_stopping_plan("peto", n_interims))
    assert plan.interim_p_thresholds == (PETO_INTERIM,) * n_interims
    assert plan.final_p_threshold == PETO_FINAL


@pytest.mark.parametrize("n_interims", [1, 2, 3, 4, 5])
def test_pocock_plan_matches_legacy_table(n_interims: int) -> None:
    plan = plan_of(make_stopping_plan("pocock", n_interims))
    assert plan.interim_p_thresholds == (POCOCK[n_interims],) * n_interims
    assert plan.final_p_threshold == POCOCK[n_interims]


@pytest.mark.parametrize("n_interims", [1, 2, 3, 4, 5])
def test_obrien_fleming_plan_matches_legacy_table(n_interims: int) -> None:
    plan = plan_of(make_stopping_plan("obrien_fleming", n_interims))
    interims, final = OBF[n_interims]
    assert plan.interim_p_thresholds == interims
    assert plan.final_p_threshold == final


def test_default_information_fractions_equally_spaced() -> None:
    plan = plan_of(make_stopping_plan("peto", 3))
    assert plan.information_fractions == (0.25, 0.5, 0.75)


def test_custom_plan_roundtrip() -> None:
    plan = plan_of(
        make_stopping_plan(
            "custom",
            2,
            information_fractions=(0.3, 0.6),
            interim_p_thresholds=(0.01, 0.02),
            final_p_threshold=0.04,
            stop_for="benefit",
            minimum_total_events=20,
        )
    )
    assert plan.information_fractions == (0.3, 0.6)
    assert plan.interim_p_thresholds == (0.01, 0.02)
    assert plan.final_p_threshold == 0.04
    assert plan.stop_for == "benefit"
    assert plan.minimum_total_events == 20


def test_plan_validation_errors() -> None:
    assert "invalid_stopping_rule" in codes_of(make_stopping_plan("haybittle", 3))
    assert "stopping_interims_out_of_range" in codes_of(make_stopping_plan("peto", 0))
    assert "stopping_interims_out_of_range" in codes_of(make_stopping_plan("pocock", 6))
    assert "stopping_threshold_missing" in codes_of(make_stopping_plan("custom", 2))
    assert "stopping_threshold_length_mismatch" in codes_of(
        make_stopping_plan(
            "custom", 3, interim_p_thresholds=(0.001, 0.01), final_p_threshold=0.05
        )
    )
    assert "stopping_threshold_out_of_bounds" in codes_of(
        make_stopping_plan(
            "custom", 1, interim_p_thresholds=(1.5,), final_p_threshold=0.05
        )
    )
    assert "stopping_fractions_invalid" in codes_of(
        make_stopping_plan("peto", 2, information_fractions=(0.6, 0.3))
    )
    assert "stopping_thresholds_only_for_custom" in codes_of(
        make_stopping_plan("peto", 2, interim_p_thresholds=(0.01, 0.01))
    )
    assert "invalid_stop_for" in codes_of(make_stopping_plan("peto", 2, stop_for="futility"))


# --- stopping plan inside a trial definition -------------------------------------------------


def stopping_trial(total_n: int = 800, n_simulations: int = 4000, **kw: Any) -> ValidatedTrial:
    stopping = kw.pop("stopping", {"enabled": True, "rule": "peto", "n_interims": 3})
    return make_validated(
        allocation={"total_n": total_n, "intervention_fraction": 0.5},
        n_simulations=n_simulations,
        stopping=stopping,
        **kw,
    )


def test_stopping_block_parses_into_definition() -> None:
    validated = stopping_trial()
    plan = validated.definition.stopping
    assert isinstance(plan, StoppingPlan)
    assert plan.rule == "peto"
    assert plan.information_fractions == (0.25, 0.5, 0.75)


def test_disabled_stopping_parses_to_none() -> None:
    validated = stopping_trial(stopping={"enabled": False, "rule": "peto", "n_interims": 3})
    assert validated.definition.stopping is None


def test_invalid_stopping_block_rejected() -> None:
    raw = make_raw(
        stopping={
            "rule": "custom",
            "n_interims": 3,
            "interim_p_thresholds": [0.001, 0.01],
            "final_p_threshold": 0.05,
        }
    )
    result = validate_trial_definition(raw)
    assert isinstance(result, tuple)
    assert any(e.code == "stopping_threshold_length_mismatch" for e in result)


# --- stopping simulation (SPEC §11.3-§11.4) --------------------------------------------------


def test_look_sample_sizes_are_cumulative_and_end_at_full_n() -> None:
    result = simulate_with_stopping(stopping_trial(n_simulations=200))
    assert result.look_sample_sizes == ((100, 100), (200, 200), (300, 300), (400, 400))


def test_strong_effect_stops_early_for_benefit() -> None:
    result = simulate_with_stopping(
        stopping_trial(
            arms={
                "control": {"event_probability": 0.20},
                "intervention": {"event_probability": 0.05},
            }
        )
    )
    summary = result.summary
    assert summary.proportion_stopped_any > 0.5
    assert summary.proportion_stopped_benefit > 10 * summary.proportion_stopped_harm
    assert summary.mean_fraction_at_stop is not None
    assert 0.0 < summary.mean_fraction_at_stop < 1.0
    assert summary.final_power_including_stops > 0.95


def test_by_look_proportions_sum_to_stopped_any() -> None:
    result = simulate_with_stopping(stopping_trial())
    summary = result.summary
    assert len(summary.proportion_stopped_by_look) == 3
    assert math.isclose(
        sum(summary.proportion_stopped_by_look), summary.proportion_stopped_any, abs_tol=1e-12
    )


def test_minimum_total_events_blocks_interim_stops() -> None:
    result = simulate_with_stopping(
        stopping_trial(
            stopping={
                "rule": "peto",
                "n_interims": 3,
                "minimum_total_events": 10_000,  # unreachable
            }
        )
    )
    assert result.summary.proportion_stopped_any == 0.0
    assert result.summary.mean_fraction_at_stop is None
    # The final analysis still runs, so power survives.
    assert result.summary.final_power_including_stops > 0.9


def test_stop_for_direction_is_respected() -> None:
    harmful_arms = {
        "control": {"event_probability": 0.10},
        "intervention": {"event_probability": 0.20},
    }
    benefit_only = simulate_with_stopping(
        stopping_trial(
            arms=harmful_arms,
            stopping={"rule": "peto", "n_interims": 3, "stop_for": "benefit"},
        )
    )
    assert benefit_only.summary.proportion_stopped_any < 0.01
    harm_only = simulate_with_stopping(
        stopping_trial(
            arms=harmful_arms,
            stopping={"rule": "peto", "n_interims": 3, "stop_for": "harm"},
        )
    )
    assert harm_only.summary.proportion_stopped_harm > 0.2
    assert harm_only.summary.proportion_stopped_benefit < 0.005


def test_power_including_stops_close_to_fixed_design_power() -> None:
    """Peto thresholds barely spend alpha early, so power stays near the fixed design."""
    fixed = simulate_trial(
        make_validated(
            allocation={"total_n": 800, "intervention_fraction": 0.5}, n_simulations=4000
        )
    )
    stopped = simulate_with_stopping(stopping_trial())
    assert abs(stopped.summary.final_power_including_stops - fixed.summary.power) < 0.03


def test_type_i_error_including_stops_near_alpha() -> None:
    result = simulate_with_stopping(
        stopping_trial(n_simulations=5000), include_type_i_error=True
    )
    type_i = result.summary.type_i_error_including_stops
    assert type_i is not None
    assert abs(type_i - 0.05) < 0.02
    # Without the flag it is not computed.
    assert (
        simulate_with_stopping(stopping_trial(n_simulations=200)).summary
        .type_i_error_including_stops
        is None
    )


def test_stopping_simulation_is_seed_reproducible() -> None:
    a = simulate_with_stopping(stopping_trial(n_simulations=1000))
    b = simulate_with_stopping(stopping_trial(n_simulations=1000))
    assert np.array_equal(a.stopped, b.stopped)
    assert np.array_equal(a.look_at_stop, b.look_at_stop)
    assert np.array_equal(a.direction_at_stop, b.direction_at_stop)


def test_stopping_works_with_imperfections() -> None:
    result = simulate_with_stopping(
        stopping_trial(
            imperfections={
                "control": {"loss_probability": 0.1},
                "intervention": {"loss_probability": 0.1, "noncompliance_probability": 0.2},
            }
        )
    )
    assert 0.0 <= result.summary.final_power_including_stops <= 1.0
    assert result.summary.proportion_stopped_any >= 0.0


def test_trial_without_stopping_plan_is_rejected() -> None:
    with pytest.raises(ValueError, match="stopping"):
        simulate_with_stopping(make_validated())
