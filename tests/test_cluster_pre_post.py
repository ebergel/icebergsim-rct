"""Pre/post cluster randomized trial simulation (SPEC §2.8, §15 — the v2.1 feature).

The generative model is chosen to match the §15.1 formula's variance algebra exactly:
cluster latent rates have between-cluster variance ICC*p*(1-p) and pre/post correlation
corr; the primary analysis is a cluster-level change-score t-test — so formula-based and
simulation-based power must agree (§2.8), which is the key test below.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from icebergsim.cluster_pre_post import (
    ClusterPrePostResult,
    simulate_cluster_pre_post,
    validate_cluster_pre_post_trial,
)
from icebergsim.model import (
    ClusterPrePostSampleSizeResult,
    ClusterPrePostTrialDefinition,
)
from icebergsim.sample_size import calculate_cluster_pre_post_sample_size


def pre_post_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "icebergsim.trial.v2",
        "id": "pre_post_test",
        "label": "Pre/post cluster trial",
        "mode": "cluster_pre_post",
        "n_simulations": 4000,
        "random_seed": 606,
        "alpha": 0.05,
        "arms": {
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.10},
        },
        "baseline_event_probability": 0.20,
        "clusters": {
            "control_clusters": 8,
            "intervention_clusters": 8,
            "mean_cluster_size": 100,
            "cluster_size_distribution": {"type": "fixed"},
        },
        "icc": 0.01,
        "pre_post_correlation": 0.5,
    }
    raw.update(overrides)
    return raw


def validated(**overrides: Any) -> ClusterPrePostTrialDefinition:
    result = validate_cluster_pre_post_trial(pre_post_raw(**overrides))
    assert isinstance(result, ClusterPrePostTrialDefinition), result
    return result


def codes(raw: dict[str, Any]) -> list[str]:
    result = validate_cluster_pre_post_trial(raw)
    assert isinstance(result, tuple), f"expected errors, got {result}"
    return [e.code for e in result]


# --- validation ------------------------------------------------------------------------------


def test_valid_definition_parses() -> None:
    definition = validated()
    assert definition.pre_post_correlation == 0.5
    assert definition.baseline_event_probability == 0.20
    assert definition.control_clusters == 8


def test_baseline_defaults_to_control_probability() -> None:
    raw = pre_post_raw()
    del raw["baseline_event_probability"]
    definition = validate_cluster_pre_post_trial(raw)
    assert isinstance(definition, ClusterPrePostTrialDefinition)
    assert definition.baseline_event_probability == 0.20


def test_validation_errors() -> None:
    assert "invalid_mode" in codes(pre_post_raw(mode="cluster_post"))
    assert "correlation_out_of_bounds" in codes(pre_post_raw(pre_post_correlation=1.5))
    assert "icc_out_of_bounds" in codes(pre_post_raw(icc=1.0))
    assert "probability_out_of_bounds" in codes(pre_post_raw(baseline_event_probability=1.2))
    assert "cluster_count_too_small" in codes(
        pre_post_raw(
            clusters={
                "control_clusters": 1,
                "intervention_clusters": 8,
                "mean_cluster_size": 100,
            }
        )
    )


# --- rate generation -------------------------------------------------------------------------


def test_period_means_match_inputs() -> None:
    result = simulate_cluster_pre_post(validated())
    summary = result.summary
    assert math.isclose(summary.mean_baseline_cer, 0.20, abs_tol=0.01)
    assert math.isclose(summary.mean_baseline_eer, 0.20, abs_tol=0.01)  # both arms at baseline
    assert math.isclose(summary.mean_followup_cer, 0.20, abs_tol=0.01)
    assert math.isclose(summary.mean_followup_eer, 0.10, abs_tol=0.01)
    # Gaussian latent rates always have thin tails beyond [0,1]; here the mass is
    # negligible (~4e-4 per draw at p=0.1, ICC=0.01) but never exactly zero.
    assert summary.truncated_rate_fraction < 0.001


def test_pre_post_correlation_is_realized_with_binomial_attenuation() -> None:
    """Observed cluster proportions correlate at corr * S2_b / (S2_b + S2_w/m)."""
    definition = validated(
        n_simulations=3000,
        arms={
            "control": {"event_probability": 0.5},
            "intervention": {"event_probability": 0.5},
        },
        baseline_event_probability=0.5,
        clusters={
            "control_clusters": 8,
            "intervention_clusters": 8,
            # m = 50 makes the attenuation strong (0.6 -> ~0.435), so a generator
            # without binomial attenuation cannot slip inside the tolerance.
            "mean_cluster_size": 50,
            "cluster_size_distribution": {"type": "fixed"},
        },
        icc=0.05,
        pre_post_correlation=0.6,
    )
    result = simulate_cluster_pre_post(definition)
    pre = np.asarray(result.arrays.control_pre_proportions, dtype=np.float64).ravel()
    post = np.asarray(result.arrays.control_post_proportions, dtype=np.float64).ravel()
    observed = float(np.corrcoef(pre, post)[0, 1])
    s2_between = 0.05 * 0.25
    s2_within = 0.25 - s2_between
    expected = 0.6 * s2_between / (s2_between + s2_within / 50)
    assert math.isclose(observed, expected, abs_tol=0.03)


def test_mild_truncation_is_reported_not_silent() -> None:
    # p=0.1, ICC=0.03: expected truncated mass ~2.7% — allowed, but must be disclosed.
    result = simulate_cluster_pre_post(
        validated(
            arms={
                "control": {"event_probability": 0.10},
                "intervention": {"event_probability": 0.10},
            },
            baseline_event_probability=0.10,
            icc=0.03,
            n_simulations=500,
        )
    )
    assert result.summary.truncated_rate_fraction > 0.005
    assert any("truncat" in warning for warning in result.warnings)
    assert any("means and effect sizes" in warning for warning in result.warnings)


def test_excessive_truncation_is_rejected_at_validation() -> None:
    """AXIOMS §4: a design whose clipping would materially bias realized means is
    rejected with the exact constraint violation, never silently distorted."""
    error_codes = codes(
        pre_post_raw(
            arms={
                "control": {"event_probability": 0.03},
                "intervention": {"event_probability": 0.03},
            },
            baseline_event_probability=0.03,
            icc=0.20,  # ~35% of latent mass below zero: realized rate would double
        )
    )
    assert "cluster_rate_truncation_excessive" in error_codes


# --- operating characteristics (SPEC §2.8: formula and simulation must agree) ----------------


def test_simulated_power_agrees_with_the_formula_design() -> None:
    """Simulate at the §15.1 formula's design; change-score power must be near target."""
    formula = calculate_cluster_pre_post_sample_size(
        p_control=0.20,
        p_intervention=0.10,
        alpha=0.05,
        power=0.80,
        mean_cluster_size=100,
        icc=0.01,
        pre_post_correlation=0.5,
    )
    assert isinstance(formula, ClusterPrePostSampleSizeResult)
    definition = validated(
        clusters={
            "control_clusters": formula.clusters_per_arm,
            "intervention_clusters": formula.clusters_per_arm,
            "mean_cluster_size": 100,
            "cluster_size_distribution": {"type": "fixed"},
        }
    )
    result = simulate_cluster_pre_post(definition)
    # True power here is ~0.813 (slightly ABOVE nominal: ceil() grants 800 individuals
    # per arm vs the unrounded 748.5, and the intervention arm's mu-based variance is
    # smaller — together outweighing the t-vs-z penalty at df 14). The band is tight
    # enough to catch a generator that drops the correlation term (power ~0.695).
    assert 0.72 <= result.summary.power_change_score <= 0.88


def test_baseline_adjustment_beats_followup_only_when_cluster_variance_dominates() -> None:
    """Change scores double the binomial noise S2_w/m but cancel 2*corr*S2_b of the
    cluster variance, so they beat follow-up-only iff corr > (S2_b + S2_w/m)/(2*S2_b).
    At ICC=0.05, m=100 that threshold is ~0.6, so corr=0.8 wins; at ICC=0.01 it cannot.
    """
    higher_rates = {
        # Rates away from the boundary keep expected truncation ~1% at ICC=0.05.
        "arms": {
            "control": {"event_probability": 0.30},
            "intervention": {"event_probability": 0.20},
        },
        "baseline_event_probability": 0.30,
    }
    dominated = simulate_cluster_pre_post(
        validated(icc=0.05, pre_post_correlation=0.8, n_simulations=4000, **higher_rates)
    )
    assert dominated.summary.power_change_score > dominated.summary.power_followup_only
    # At ICC=0.01 the same correlation is NOT enough: follow-up-only stays ahead.
    noisy = simulate_cluster_pre_post(
        validated(icc=0.01, pre_post_correlation=0.8, **higher_rates)
    )
    assert noisy.summary.power_followup_only > noisy.summary.power_change_score


def test_higher_correlation_increases_change_score_power() -> None:
    low = simulate_cluster_pre_post(validated(pre_post_correlation=0.0))
    high = simulate_cluster_pre_post(validated(pre_post_correlation=0.8))
    assert high.summary.power_change_score > low.summary.power_change_score + 0.05
    # Follow-up-only power does not depend on the pre/post correlation.
    assert math.isclose(
        high.summary.power_followup_only, low.summary.power_followup_only, abs_tol=0.04
    )


def test_null_type_i_error_near_alpha() -> None:
    null = simulate_cluster_pre_post(
        validated(
            arms={
                "control": {"event_probability": 0.20},
                "intervention": {"event_probability": 0.20},
            },
            n_simulations=5000,
        )
    )
    assert 0.02 <= null.summary.power_change_score <= 0.09
    assert abs(null.summary.mean_did) < 0.01


# --- result contract -------------------------------------------------------------------------


def test_reproducible_and_carries_manifest() -> None:
    a = simulate_cluster_pre_post(validated(n_simulations=500))
    b = simulate_cluster_pre_post(validated(n_simulations=500))
    assert isinstance(a, ClusterPrePostResult)
    assert np.array_equal(a.arrays.p_change_score, b.arrays.p_change_score)
    assert np.array_equal(a.arrays.did, b.arrays.did)
    assert a.rng_algorithm == "PCG64"
    assert a.spec_version == "2.0.0-alpha.1"
    assert len(a.input_hash) == 64
    assert any("change-score" in note for note in a.notes)


def test_did_sign_convention_matches_benefit() -> None:
    """Beneficial intervention (fewer follow-up events) gives positive DiD, like ARR."""
    result = simulate_cluster_pre_post(validated())
    assert result.summary.mean_did > 0.05  # control change - intervention change ~ 0.10
