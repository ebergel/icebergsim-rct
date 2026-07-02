"""Post-only cluster randomized trials (SPEC §14): beta-binomial generation and analyses."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from icebergsim.cluster import (
    ClusterSimulationResult,
    beta_binomial_parameters,
    simulate_cluster_post_only,
    validate_cluster_trial,
)
from icebergsim.model import ClusterTrialDefinition, ValidationError

Errors = tuple[ValidationError, ...]


def cluster_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "icebergsim.trial.v2",
        "id": "cluster_test",
        "label": "Cluster test trial",
        "mode": "cluster_post",
        "n_simulations": 20000,
        "random_seed": 909,
        "alpha": 0.05,
        "arms": {
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.10},
        },
        "clusters": {
            "control_clusters": 4,
            "intervention_clusters": 4,
            "mean_cluster_size": 100,
            "cluster_size_distribution": {"type": "fixed"},
        },
        "icc": 0.01,
    }
    raw.update(overrides)
    return raw


def validated_cluster(**overrides: Any) -> ClusterTrialDefinition:
    result = validate_cluster_trial(cluster_raw(**overrides))
    assert isinstance(result, ClusterTrialDefinition), result
    return result


def cluster_codes(raw: dict[str, Any]) -> list[str]:
    result = validate_cluster_trial(raw)
    assert isinstance(result, tuple), f"expected errors, got {result}"
    return [e.code for e in result]


# --- beta-binomial parameters (SPEC §14.3) ---------------------------------------------------


def test_beta_parameters_canonical() -> None:
    alpha, beta = beta_binomial_parameters(0.20, 0.01)
    assert isinstance(alpha, float) and isinstance(beta, float)
    assert math.isclose(alpha, 19.8, abs_tol=1e-12)
    assert math.isclose(beta, 79.2, abs_tol=1e-12)


def test_beta_parameters_symmetric_case() -> None:
    alpha, beta = beta_binomial_parameters(0.5, 0.5)
    assert isinstance(alpha, float) and isinstance(beta, float)
    assert math.isclose(alpha, 0.5, abs_tol=1e-12)
    assert math.isclose(beta, 0.5, abs_tol=1e-12)


def test_beta_parameters_reject_degenerate_inputs() -> None:
    for p, icc in ((0.2, 0.0), (0.2, 1.0), (0.0, 0.01), (1.0, 0.01)):
        result = beta_binomial_parameters(p, icc)
        assert isinstance(result, tuple)
        assert all(isinstance(e, ValidationError) for e in result), (p, icc)


# --- validation ------------------------------------------------------------------------------


def test_valid_cluster_trial_parses() -> None:
    defn = validated_cluster()
    assert defn.control_clusters == 4
    assert defn.intervention_clusters == 4
    assert defn.mean_cluster_size == 100
    assert defn.icc == 0.01
    assert defn.p_control == 0.20
    assert defn.size_distribution.type == "fixed"


def test_cluster_validation_errors() -> None:
    assert "invalid_mode" in cluster_codes(cluster_raw(mode="individual_binary"))
    assert "icc_out_of_bounds" in cluster_codes(cluster_raw(icc=1.0))
    assert "cluster_count_too_small" in cluster_codes(
        cluster_raw(clusters={"control_clusters": 1, "intervention_clusters": 4,
                              "mean_cluster_size": 100})
    )
    assert "probability_out_of_bounds" in cluster_codes(
        cluster_raw(arms={"control": {"event_probability": 1.5},
                          "intervention": {"event_probability": 0.1}})
    )
    assert "cluster_size_distribution_not_supported" in cluster_codes(
        cluster_raw(clusters={"control_clusters": 4, "intervention_clusters": 4,
                              "mean_cluster_size": 100,
                              "cluster_size_distribution": {"type": "legacy_beta_size"}})
    )
    assert "cluster_size_sd_required" in cluster_codes(
        cluster_raw(clusters={"control_clusters": 4, "intervention_clusters": 4,
                              "mean_cluster_size": 100,
                              "cluster_size_distribution": {"type": "lognormal"}})
    )
    assert "cluster_size_sd_too_small" in cluster_codes(
        cluster_raw(clusters={"control_clusters": 4, "intervention_clusters": 4,
                              "mean_cluster_size": 100,
                              "cluster_size_distribution": {"type": "negative_binomial",
                                                            "sd": 5.0}})
    )


# --- cluster size generation -----------------------------------------------------------------


def test_fixed_sizes_are_constant() -> None:
    result = simulate_cluster_post_only(validated_cluster(n_simulations=200))
    assert np.all(result.tables.control_observed == 400)  # 4 clusters x 100
    assert np.all(result.tables.intervention_observed == 400)


def test_poisson_sizes_vary_around_mean() -> None:
    defn = validated_cluster(
        n_simulations=2000,
        clusters={
            "control_clusters": 4,
            "intervention_clusters": 4,
            "mean_cluster_size": 100,
            "cluster_size_distribution": {"type": "poisson"},
        },
    )
    result = simulate_cluster_post_only(defn)
    observed = np.asarray(result.tables.control_observed, dtype=np.float64)
    assert observed.std() > 0.0
    assert math.isclose(float(observed.mean()), 400.0, abs_tol=2.0)
    assert np.all(observed >= 4)  # min cluster size 1


# --- beta-binomial event generation (SPEC §14.3) ---------------------------------------------


def test_icc_zero_matches_independent_binomial() -> None:
    result = simulate_cluster_post_only(validated_cluster(icc=0.0))
    events = np.asarray(result.tables.control_events, dtype=np.float64)
    # Binomial(400, 0.2): mean 80, var 64.
    assert math.isclose(float(events.mean()), 80.0, abs_tol=1.0)
    assert abs(float(events.var()) / 64.0 - 1.0) < 0.15


def test_icc_inflates_event_count_variance_by_design_effect() -> None:
    """Per-cluster beta-binomial variance: m*p*q * (1 + (m-1)*icc)."""
    result = simulate_cluster_post_only(validated_cluster())
    events = np.asarray(result.tables.control_events, dtype=np.float64)
    expected_var = 4 * 100 * 0.2 * 0.8 * (1.0 + 99 * 0.01)  # 127.36
    assert math.isclose(float(events.mean()), 80.0, abs_tol=1.5)
    assert abs(float(events.var()) / expected_var - 1.0) < 0.20


def test_mean_rates_preserved_under_clustering() -> None:
    result = simulate_cluster_post_only(validated_cluster())
    assert math.isclose(result.summary.mean_cer, 0.20, abs_tol=0.01)
    assert math.isclose(result.summary.mean_eer, 0.10, abs_tol=0.01)


# --- the three required analyses (SPEC §14.4, AXIOMS §11) ------------------------------------


def test_unadjusted_analysis_is_anticonservative_under_null() -> None:
    null = validated_cluster(
        n_simulations=4000,
        icc=0.05,
        arms={
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.20},
        },
        clusters={
            "control_clusters": 10,
            "intervention_clusters": 10,
            "mean_cluster_size": 100,
        },
    )
    result = simulate_cluster_post_only(null)
    summary = result.summary
    # Design effect 1 + 99*0.05 = 5.95: the naive chi-square rejects far too often...
    assert summary.power_unadjusted_chi_square > 0.15
    # ...while the design-effect adjustment and the cluster-level t-test hold near alpha.
    assert summary.power_adjusted_chi_square < 0.12
    assert 0.02 < summary.power_cluster_level_difference < 0.10
    # AXIOMS §11: the unadjusted analysis must be labeled.
    assert any("anti-conservative" in note for note in result.notes)


def test_real_effect_detected_and_orderings_hold() -> None:
    result = simulate_cluster_post_only(validated_cluster(n_simulations=4000))
    summary = result.summary
    # Canonical sample-size case says 4 clusters x 100 gives ~80% power at icc=0.01.
    assert 0.5 < summary.power_adjusted_chi_square < 0.95
    assert summary.power_unadjusted_chi_square >= summary.power_adjusted_chi_square
    assert summary.mean_cluster_level_difference > 0.05  # CER - EER ~ 0.10
    assert math.isclose(summary.mean_design_effect, 1.99, abs_tol=1e-9)  # fixed sizes


def test_cluster_simulation_reproducible_and_carries_manifest() -> None:
    a = simulate_cluster_post_only(validated_cluster(n_simulations=500))
    b = simulate_cluster_post_only(validated_cluster(n_simulations=500))
    assert isinstance(a, ClusterSimulationResult)
    assert np.array_equal(a.tables.control_events, b.tables.control_events)
    assert np.array_equal(a.arrays.p_cluster_level, b.arrays.p_cluster_level)
    assert a.rng_algorithm == "PCG64"
    assert a.spec_version == "2.0.0-alpha.1"
    assert len(a.input_hash) == 64


def test_cluster_level_ci_contains_difference() -> None:
    result = simulate_cluster_post_only(validated_cluster(n_simulations=500))
    arrays = result.arrays
    assert np.all(arrays.cluster_level_ci_low <= arrays.cluster_level_difference)
    assert np.all(arrays.cluster_level_difference <= arrays.cluster_level_ci_high)
    assert np.all((arrays.p_cluster_level >= 0.0) & (arrays.p_cluster_level <= 1.0))
