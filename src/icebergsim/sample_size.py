"""Formula sample-size calculations (SPEC §10, §14.2, §15.1).

Pure functions returning frozen results or a tuple of ValidationErrors. Each result states
the formula used (SPEC §10.2). These are the conventional normal-approximation formulas;
achieved power under imperfections is estimated separately by Monte Carlo simulation.
"""

from __future__ import annotations

import math

from scipy import stats

from icebergsim.model import (
    ClusterPostSampleSizeResult,
    ClusterPrePostSampleSizeResult,
    TwoArmSampleSizeResult,
    ValidationError,
)
from icebergsim.model import (
    validation_error as _error,
)

Errors = tuple[ValidationError, ...]

ALTERNATIVES = ("two_sided", "superiority_one_sided", "noninferiority_one_sided")


def calculate_two_arm_sample_size(
    p_control: float,
    p_intervention: float,
    alpha: float = 0.05,
    power: float = 0.80,
    alternative: str = "two_sided",
    allocation_ratio_intervention_to_control: float = 1.0,
) -> TwoArmSampleSizeResult | Errors:
    """Normal-approximation sample size for two independent proportions (SPEC §10.1/§10.2).

    For allocation ratio r = n_intervention / n_control:

        n_control      = ceil((z_alpha + z_beta)^2 * [pc(1-pc) + pi(1-pi)/r] / (pc - pi)^2)
        n_intervention = ceil(r * n_control)

    With r = 1 this reduces exactly to the equal-allocation formula of §10.1.
    """
    errors = _check_common_inputs(p_control, p_intervention, alpha, power, alternative)
    if allocation_ratio_intervention_to_control <= 0.0:
        errors += (
            _error(
                "allocation_ratio_not_positive",
                "allocation_ratio_intervention_to_control must be > 0.",
                "allocation_ratio_intervention_to_control",
            ),
        )
    if errors:
        return errors

    r = allocation_ratio_intervention_to_control
    z_sum = _z_alpha(alpha, alternative) + _z_beta(power)
    variance = p_control * (1.0 - p_control) + p_intervention * (1.0 - p_intervention) / r
    unrounded_n_control = z_sum**2 * variance / (p_control - p_intervention) ** 2
    n_control = math.ceil(unrounded_n_control)
    n_intervention = math.ceil(r * n_control)
    return TwoArmSampleSizeResult(
        n_control=n_control,
        n_intervention=n_intervention,
        n_total=n_control + n_intervention,
        unrounded_n_control=unrounded_n_control,
        unrounded_n_intervention=r * unrounded_n_control,
        allocation_ratio_intervention_to_control=r,
        formula="normal_approximation_two_proportions (SPEC §10.1/§10.2)",
    )


def calculate_cluster_post_sample_size(
    p_control: float,
    p_intervention: float,
    alpha: float = 0.05,
    power: float = 0.80,
    alternative: str = "two_sided",
    *,
    mean_cluster_size: float,
    icc: float,
) -> ClusterPostSampleSizeResult | Errors:
    """Design-effect adjusted sample size for post-only cluster trials (SPEC §14.2).

        design_effect   = 1 + (m - 1) * ICC
        n_adjusted      = n_per_arm_individual_unrounded * design_effect
        clusters_per_arm = ceil(n_adjusted / m)
    """
    errors = _check_common_inputs(p_control, p_intervention, alpha, power, alternative)
    errors += _check_cluster_inputs(mean_cluster_size, icc)
    if errors:
        return errors

    individual = calculate_two_arm_sample_size(
        p_control, p_intervention, alpha, power, alternative
    )
    assert isinstance(individual, TwoArmSampleSizeResult)  # inputs already validated
    design_effect = 1.0 + (mean_cluster_size - 1.0) * icc
    adjusted_unrounded = individual.unrounded_n_control * design_effect
    return ClusterPostSampleSizeResult(
        individual_n_per_arm_unrounded=individual.unrounded_n_control,
        design_effect=design_effect,
        cluster_adjusted_n_per_arm_unrounded=adjusted_unrounded,
        n_per_arm_cluster_adjusted=math.ceil(adjusted_unrounded),
        clusters_per_arm=math.ceil(adjusted_unrounded / mean_cluster_size),
        formula="design_effect_1_plus_m_minus_1_icc (SPEC §14.2)",
    )


def calculate_cluster_pre_post_sample_size(
    p_control: float,
    p_intervention: float,
    alpha: float = 0.05,
    power: float = 0.80,
    alternative: str = "two_sided",
    *,
    mean_cluster_size: float,
    icc: float,
    pre_post_correlation: float,
) -> ClusterPrePostSampleSizeResult | Errors:
    """Historical pre/post cluster formula, preserved verbatim (SPEC §15.1).

        S2_between = ICC * pc * (1 - pc)
        S2_within  = pc * (1 - pc) - S2_between
        n_per_arm  = 4 * [S2_within + m * S2_between * (1 - corr)] * (z_a + z_b)^2 / (pc - pi)^2
    """
    errors = _check_common_inputs(p_control, p_intervention, alpha, power, alternative)
    errors += _check_cluster_inputs(mean_cluster_size, icc)
    if not 0.0 <= pre_post_correlation <= 1.0:
        errors += (
            _error(
                "correlation_out_of_bounds",
                "pre_post_correlation must be in [0, 1].",
                "pre_post_correlation",
            ),
        )
    if errors:
        return errors

    z_sum = _z_alpha(alpha, alternative) + _z_beta(power)
    s2_between = icc * p_control * (1.0 - p_control)
    s2_within = p_control * (1.0 - p_control) - s2_between
    n_per_arm_unrounded = (
        4.0
        * (s2_within + mean_cluster_size * s2_between * (1.0 - pre_post_correlation))
        * z_sum**2
        / (p_control - p_intervention) ** 2
    )
    return ClusterPrePostSampleSizeResult(
        n_per_arm_unrounded=n_per_arm_unrounded,
        n_per_arm=math.ceil(n_per_arm_unrounded),
        clusters_per_arm=math.ceil(n_per_arm_unrounded / mean_cluster_size),
        formula="historical_pre_post_cluster (SPEC §15.1)",
    )


# --- shared input checks and quantiles ------------------------------------------------------


def _check_common_inputs(
    p_control: float, p_intervention: float, alpha: float, power: float, alternative: str
) -> Errors:
    errors: list[ValidationError] = []
    for value, path in ((p_control, "p_control"), (p_intervention, "p_intervention")):
        if not 0.0 <= value <= 1.0:
            errors.append(
                _error(
                    "probability_out_of_bounds", f"{path} = {value:g} is outside [0, 1].", path
                )
            )
    if not 0.0 < alpha < 1.0:
        errors.append(
            _error("alpha_out_of_bounds", "alpha must be strictly between 0 and 1.", "alpha")
        )
    if not 0.0 < power < 1.0:
        errors.append(
            _error("power_out_of_bounds", "power must be strictly between 0 and 1.", "power")
        )
    if alternative not in ALTERNATIVES:
        errors.append(
            _error(
                "invalid_alternative",
                f"alternative must be one of {ALTERNATIVES}, got {alternative!r}.",
                "alternative",
            )
        )
    if not errors and p_control == p_intervention:
        errors.append(
            _error(
                "effect_size_zero",
                "p_control and p_intervention must differ; sample size is undefined.",
                "p_intervention",
            )
        )
    return tuple(errors)


def _check_cluster_inputs(mean_cluster_size: float, icc: float) -> Errors:
    errors: list[ValidationError] = []
    if mean_cluster_size < 1.0:
        errors.append(
            _error(
                "cluster_size_not_positive",
                "mean_cluster_size must be >= 1.",
                "mean_cluster_size",
            )
        )
    if not 0.0 <= icc <= 1.0:
        errors.append(_error("icc_out_of_bounds", "icc must be in [0, 1].", "icc"))
    return tuple(errors)


def _z_alpha(alpha: float, alternative: str) -> float:
    """z_(1-alpha/2) for two-sided tests, z_(1-alpha) for one-sided (SPEC §10.1)."""
    if alternative == "two_sided":
        return float(stats.norm.ppf(1.0 - alpha / 2.0))
    return float(stats.norm.ppf(1.0 - alpha))


def _z_beta(power: float) -> float:
    return float(stats.norm.ppf(power))
