"""Sample-size formulas (SPEC §10, §14.2, §15.1).

Formula tests recompute the spec formulas independently inside the test.
"""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st
from scipy import stats

from icebergsim.model import (
    ClusterPostSampleSizeResult,
    ClusterPrePostSampleSizeResult,
    TwoArmSampleSizeResult,
    ValidationError,
)
from icebergsim.sample_size import (
    calculate_cluster_post_sample_size,
    calculate_cluster_pre_post_sample_size,
    calculate_two_arm_sample_size,
)

Z_975 = float(stats.norm.ppf(0.975))
Z_95 = float(stats.norm.ppf(0.95))
Z_80 = float(stats.norm.ppf(0.80))


def spec_10_1_unrounded_n_per_arm(
    p_control: float, p_intervention: float, z_alpha: float, z_beta: float
) -> float:
    variance = p_control * (1 - p_control) + p_intervention * (1 - p_intervention)
    return (z_alpha + z_beta) ** 2 * variance / (p_control - p_intervention) ** 2


# --- two-arm --------------------------------------------------------------------------------


def test_two_sided_equal_allocation_canonical() -> None:
    result = calculate_two_arm_sample_size(
        p_control=0.20, p_intervention=0.10, alpha=0.05, power=0.80, alternative="two_sided"
    )
    assert isinstance(result, TwoArmSampleSizeResult)
    assert math.isclose(result.unrounded_n_control, 196.22199335872716, abs_tol=1e-9)
    assert result.n_control == 197
    assert result.n_intervention == 197
    assert result.n_total == 394


def test_one_sided_uses_z_of_one_minus_alpha() -> None:
    result = calculate_two_arm_sample_size(
        p_control=0.20,
        p_intervention=0.10,
        alpha=0.05,
        power=0.80,
        alternative="superiority_one_sided",
    )
    assert isinstance(result, TwoArmSampleSizeResult)
    expected = spec_10_1_unrounded_n_per_arm(0.20, 0.10, Z_95, Z_80)
    assert math.isclose(result.unrounded_n_control, expected, abs_tol=1e-9)
    assert result.n_control == math.ceil(expected)
    assert 150 < result.n_control < 197


def test_unequal_allocation_matches_spec_10_2() -> None:
    r = 2.0
    result = calculate_two_arm_sample_size(
        p_control=0.20,
        p_intervention=0.10,
        alpha=0.05,
        power=0.80,
        alternative="two_sided",
        allocation_ratio_intervention_to_control=r,
    )
    assert isinstance(result, TwoArmSampleSizeResult)
    variance = 0.20 * 0.80 + 0.10 * 0.90 / r
    expected_n_control = (Z_975 + Z_80) ** 2 * variance / 0.10**2
    assert math.isclose(result.unrounded_n_control, expected_n_control, abs_tol=1e-9)
    assert result.n_control == math.ceil(expected_n_control)
    assert result.n_intervention == math.ceil(r * result.n_control)
    assert result.n_total == result.n_control + result.n_intervention


def test_formula_name_is_stated() -> None:
    result = calculate_two_arm_sample_size(p_control=0.20, p_intervention=0.10)
    assert isinstance(result, TwoArmSampleSizeResult)
    assert result.formula  # SPEC §10.2: the implementation MUST state the formula used


def test_swapping_arms_preserves_equal_allocation_size() -> None:
    a = calculate_two_arm_sample_size(p_control=0.20, p_intervention=0.10)
    b = calculate_two_arm_sample_size(p_control=0.10, p_intervention=0.20)
    assert isinstance(a, TwoArmSampleSizeResult)
    assert isinstance(b, TwoArmSampleSizeResult)
    assert a.n_control == b.n_control


@given(
    power_low=st.floats(0.50, 0.94),
    power_delta=st.floats(0.01, 0.05),
)
def test_higher_power_never_needs_fewer_participants(
    power_low: float, power_delta: float
) -> None:
    low = calculate_two_arm_sample_size(p_control=0.20, p_intervention=0.10, power=power_low)
    high = calculate_two_arm_sample_size(
        p_control=0.20, p_intervention=0.10, power=power_low + power_delta
    )
    assert isinstance(low, TwoArmSampleSizeResult)
    assert isinstance(high, TwoArmSampleSizeResult)
    assert high.n_total >= low.n_total


def test_equal_probabilities_rejected() -> None:
    result = calculate_two_arm_sample_size(p_control=0.20, p_intervention=0.20)
    assert isinstance(result, tuple)
    assert any(e.code == "effect_size_zero" for e in result)


def test_invalid_inputs_rejected() -> None:
    def codes(**kwargs: object) -> list[str]:
        result = calculate_two_arm_sample_size(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, tuple)
        return [e.code for e in result]

    assert "probability_out_of_bounds" in codes(p_control=1.2, p_intervention=0.1)
    assert "alpha_out_of_bounds" in codes(p_control=0.2, p_intervention=0.1, alpha=1.0)
    assert "power_out_of_bounds" in codes(p_control=0.2, p_intervention=0.1, power=1.0)
    assert "allocation_ratio_not_positive" in codes(
        p_control=0.2, p_intervention=0.1, allocation_ratio_intervention_to_control=0.0
    )
    assert "invalid_alternative" in codes(
        p_control=0.2, p_intervention=0.1, alternative="both_sided"
    )


# --- cluster post-only (SPEC §14.2) ---------------------------------------------------------


def test_cluster_design_effect_canonical() -> None:
    result = calculate_cluster_post_sample_size(
        p_control=0.20,
        p_intervention=0.10,
        alpha=0.05,
        power=0.80,
        alternative="two_sided",
        mean_cluster_size=100,
        icc=0.01,
    )
    assert isinstance(result, ClusterPostSampleSizeResult)
    assert math.isclose(result.individual_n_per_arm_unrounded, 196.22199335872716, abs_tol=1e-9)
    assert math.isclose(result.design_effect, 1.99, abs_tol=1e-12)
    assert math.isclose(
        result.cluster_adjusted_n_per_arm_unrounded, 390.48176678386704, abs_tol=1e-9
    )
    assert result.clusters_per_arm == 4


def test_zero_icc_reduces_to_individual_sample_size() -> None:
    result = calculate_cluster_post_sample_size(
        p_control=0.20, p_intervention=0.10, mean_cluster_size=50, icc=0.0
    )
    assert isinstance(result, ClusterPostSampleSizeResult)
    assert result.design_effect == 1.0
    assert math.isclose(
        result.cluster_adjusted_n_per_arm_unrounded,
        result.individual_n_per_arm_unrounded,
        abs_tol=1e-12,
    )


def test_cluster_icc_out_of_bounds_rejected() -> None:
    result = calculate_cluster_post_sample_size(
        p_control=0.20, p_intervention=0.10, mean_cluster_size=50, icc=1.5
    )
    assert isinstance(result, tuple)
    assert all(isinstance(e, ValidationError) for e in result)
    assert any(e.code == "icc_out_of_bounds" for e in result)


# --- cluster pre/post (SPEC §15.1) ----------------------------------------------------------


def test_cluster_pre_post_matches_spec_15_1_formula() -> None:
    p_control, p_intervention, m, icc, corr = 0.20, 0.10, 100.0, 0.01, 0.5
    result = calculate_cluster_pre_post_sample_size(
        p_control=p_control,
        p_intervention=p_intervention,
        alpha=0.05,
        power=0.80,
        alternative="two_sided",
        mean_cluster_size=m,
        icc=icc,
        pre_post_correlation=corr,
    )
    assert isinstance(result, ClusterPrePostSampleSizeResult)
    s2_between = icc * p_control * (1 - p_control)
    s2_within = p_control * (1 - p_control) - s2_between
    expected_n = (
        4
        * (s2_within + m * s2_between * (1 - corr))
        * (Z_975 + Z_80) ** 2
        / (p_control - p_intervention) ** 2
    )
    assert math.isclose(result.n_per_arm_unrounded, expected_n, abs_tol=1e-9)
    assert result.clusters_per_arm == math.ceil(expected_n / m)


def test_cluster_pre_post_correlation_bounds() -> None:
    result = calculate_cluster_pre_post_sample_size(
        p_control=0.20,
        p_intervention=0.10,
        mean_cluster_size=100,
        icc=0.01,
        pre_post_correlation=1.5,
    )
    assert isinstance(result, tuple)
    assert any(e.code == "correlation_out_of_bounds" for e in result)
