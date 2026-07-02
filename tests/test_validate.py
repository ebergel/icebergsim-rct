"""Validation: derived loss probabilities (SPEC §5.3, AXIOMS §8) and trial definitions (§5)."""

from __future__ import annotations

import math
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from icebergsim.model import DerivedLossProbabilities, ValidatedTrial, ValidationError
from icebergsim.validate import derive_loss_probabilities, validate_trial_definition

Errors = tuple[ValidationError, ...]


def minimal_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "icebergsim.trial.v2",
        "id": "t",
        "label": "Test trial",
        "mode": "individual_binary",
        "n_simulations": 1000,
        "random_seed": 1,
        "alpha": 0.05,
        "arms": {
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.10},
        },
        "allocation": {"total_n": 400, "intervention_fraction": 0.5},
        "untreated_event_probability": 0.30,
    }
    raw.update(overrides)
    return raw


def error_codes(result: ValidatedTrial | Errors) -> list[str]:
    assert isinstance(result, tuple), f"expected errors, got {result}"
    return [e.code for e in result]


# --- derive_loss_probabilities -------------------------------------------------------------


def test_derived_probabilities_canonical_values() -> None:
    result = derive_loss_probabilities(0.20, 0.25, 2.0)
    assert isinstance(result, DerivedLossProbabilities)
    assert math.isclose(result.p_lost, 0.40, abs_tol=1e-12)
    assert math.isclose(result.p_nonlost, 0.13333333333333333, abs_tol=1e-12)


def test_derived_p_lost_out_of_bounds_rejected() -> None:
    result = derive_loss_probabilities(0.80, 0.50, 2.0)
    assert isinstance(result, tuple)
    (error,) = result
    assert error.type == "ValidationError"
    assert error.code == "derived_probability_out_of_bounds"
    assert "p_lost" in error.message
    assert math.isclose(error.details["derived_value"], 1.6)


def test_derived_p_nonlost_out_of_bounds_rejected() -> None:
    # p_lost = 0.5, p_nonlost = (0.2 - 0.5*0.5) / 0.5 = -0.1 -> invalid
    result = derive_loss_probabilities(0.20, 0.50, 2.5)
    assert isinstance(result, tuple)
    (error,) = result
    assert error.code == "derived_probability_out_of_bounds"
    assert "p_nonlost" in error.message


def test_loss_probability_of_one_rejected() -> None:
    result = derive_loss_probabilities(0.20, 1.0, 1.0)
    assert isinstance(result, tuple)
    (error,) = result
    assert error.code == "loss_probability_not_less_than_one"


def test_zero_loss_keeps_marginal_probability() -> None:
    result = derive_loss_probabilities(0.20, 0.0, 3.0)
    assert isinstance(result, DerivedLossProbabilities)
    assert math.isclose(result.p_lost, 0.60)  # bounded, so allowed even though no one is lost
    assert result.p_nonlost == 0.20


@given(
    p_exposure=st.floats(0.0, 1.0),
    loss_probability=st.floats(0.0, 0.99),
    lost_event_risk_ratio=st.floats(0.0, 5.0),
)
def test_derived_probabilities_preserve_marginal_risk(
    p_exposure: float, loss_probability: float, lost_event_risk_ratio: float
) -> None:
    """AXIOMS §8: L*p_lost + (1-L)*p_nonlost must equal the marginal p_exposure."""
    result = derive_loss_probabilities(p_exposure, loss_probability, lost_event_risk_ratio)
    if isinstance(result, tuple):
        assert all(e.code == "derived_probability_out_of_bounds" for e in result)
        return
    assert 0.0 <= result.p_lost <= 1.0
    assert 0.0 <= result.p_nonlost <= 1.0
    marginal = (
        loss_probability * result.p_lost + (1.0 - loss_probability) * result.p_nonlost
    )
    assert math.isclose(marginal, p_exposure, abs_tol=1e-9)


# --- validate_trial_definition -------------------------------------------------------------


def test_valid_minimal_trial_resolves_sample_sizes() -> None:
    result = validate_trial_definition(minimal_raw())
    assert isinstance(result, ValidatedTrial)
    assert result.n_control == 200
    assert result.n_intervention == 200
    assert result.definition.alpha == 0.05


def test_arm_n_overrides_allocation() -> None:
    raw = minimal_raw(
        arms={
            "control": {"event_probability": 0.20, "n": 150},
            "intervention": {"event_probability": 0.10, "n": 350},
        }
    )
    result = validate_trial_definition(raw)
    assert isinstance(result, ValidatedTrial)
    assert result.n_control == 150
    assert result.n_intervention == 350


def test_allocation_rounds_half_up() -> None:
    raw = minimal_raw(allocation={"total_n": 401, "intervention_fraction": 0.5})
    result = validate_trial_definition(raw)
    assert isinstance(result, ValidatedTrial)
    assert result.n_intervention == 201  # round(200.5) half-up, per SPEC §4.1
    assert result.n_control == 200


def test_partial_arm_n_rejected() -> None:
    raw = minimal_raw(
        arms={
            "control": {"event_probability": 0.20, "n": 150},
            "intervention": {"event_probability": 0.10},
        },
        allocation={"total_n": None, "intervention_fraction": 0.5},
    )
    assert "partial_arm_sample_size" in error_codes(validate_trial_definition(raw))


def test_all_probability_errors_collected() -> None:
    raw = minimal_raw(
        arms={
            "control": {"event_probability": 1.2},
            "intervention": {"event_probability": -0.1},
        }
    )
    codes = error_codes(validate_trial_definition(raw))
    assert codes == ["probability_out_of_bounds", "probability_out_of_bounds"]


def test_missing_sample_size_rejected() -> None:
    raw = minimal_raw(allocation={"total_n": None, "intervention_fraction": 0.5})
    assert "sample_size_missing" in error_codes(validate_trial_definition(raw))


def test_alpha_out_of_bounds_rejected() -> None:
    assert "alpha_out_of_bounds" in error_codes(validate_trial_definition(minimal_raw(alpha=0)))
    assert "alpha_out_of_bounds" in error_codes(validate_trial_definition(minimal_raw(alpha=1)))


def test_nonpositive_n_simulations_rejected() -> None:
    raw = minimal_raw(n_simulations=0)
    assert "sample_size_not_positive" in error_codes(validate_trial_definition(raw))


def test_invalid_mode_rejected() -> None:
    raw = minimal_raw(mode="cluster_diagonal")
    assert "invalid_mode" in error_codes(validate_trial_definition(raw))


def test_inconsistent_loss_multiplier_rejected_per_arm_and_exposure() -> None:
    # untreated exposure 0.3 * multiplier 4.0 = 1.2 > 1 for the control arm only.
    raw = minimal_raw(
        imperfections={
            "control": {"loss_probability": 0.1, "lost_event_risk_ratio": 4.0},
            "intervention": {},
        }
    )
    result = validate_trial_definition(raw)
    assert isinstance(result, tuple)
    assert all(e.code == "derived_probability_out_of_bounds" for e in result)
    assert any(e.details.get("assigned_arm") == "control" for e in result)
    assert all(e.details.get("assigned_arm") != "intervention" for e in result)


def test_analysis_options_parsed() -> None:
    raw = minimal_raw(
        analysis={
            "p_value_method": "pearson_chi_square",
            "include_lost_in_denominator": True,
        }
    )
    result = validate_trial_definition(raw)
    assert isinstance(result, ValidatedTrial)
    assert result.definition.analysis.p_value_method == "pearson_chi_square"
    assert result.definition.analysis.include_lost_in_denominator is True
    assert result.definition.analysis.analysis_population == "intention_to_treat_observed"


def test_unknown_p_value_method_rejected() -> None:
    raw = minimal_raw(analysis={"p_value_method": "students_t"})
    assert "invalid_p_value_method" in error_codes(validate_trial_definition(raw))


def test_unsupported_p_value_method_rejected_explicitly() -> None:
    # monte_carlo_exact is in the schema enum but this implementation does not support it;
    # SPEC §7.7 requires stating unsupported methods rather than failing silently.
    raw = minimal_raw(analysis={"p_value_method": "monte_carlo_exact"})
    assert "p_value_method_not_supported" in error_codes(validate_trial_definition(raw))


def test_unsupported_analysis_population_rejected_explicitly() -> None:
    raw = minimal_raw(analysis={"analysis_population": "as_treated"})
    assert "analysis_population_not_supported" in error_codes(validate_trial_definition(raw))
    raw = minimal_raw(analysis={"analysis_population": "sickest_first"})
    assert "invalid_analysis_population" in error_codes(validate_trial_definition(raw))


def test_non_mapping_imperfections_rejected_structurally() -> None:
    raw = minimal_raw(imperfections=["oops"])
    codes = error_codes(validate_trial_definition(raw))
    assert "invalid_type" in codes  # never an unhandled exception (SPEC §18)


def test_zero_cell_correction_of_zero_rejected() -> None:
    raw = minimal_raw(zero_cell_correction=0)
    codes = error_codes(validate_trial_definition(raw))
    assert "zero_cell_correction_not_positive" in codes


def test_unsupported_confidence_interval_method_rejected() -> None:
    raw = minimal_raw(analysis={"confidence_interval_method": "newcombe_score"})
    codes = error_codes(validate_trial_definition(raw))
    assert "confidence_interval_method_not_supported" in codes


def test_validation_never_mutates_input() -> None:
    raw = minimal_raw()
    snapshot = {**raw, "arms": {k: dict(v) for k, v in raw["arms"].items()}}
    validate_trial_definition(raw)
    assert raw == snapshot
