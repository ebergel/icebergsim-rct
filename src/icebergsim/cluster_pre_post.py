"""Pre/post cluster randomized trial simulation (SPEC §2.8, §15 — the reserved v2.1 feature).

Generative model, chosen so that the §15.1 sample-size formula and the simulation share one
variance algebra:

    latent rate per cluster and period:
        p = mu + sd(mu) * (sqrt(corr) * u + sqrt(1 - corr) * e),   sd(mu)^2 = ICC * mu * (1-mu)
    with u a persistent cluster effect and e a period-specific effect (both standard normal),
    so Var(p) = ICC * mu * (1-mu) = S2_between and Corr(p_pre, p_post) = corr exactly.
    Observed events per period ~ Binomial(cluster_size, p).

Both arms share the baseline mean (randomized at baseline); the arm effect applies at
follow-up. Latent rates falling outside [0, 1] are truncated and the truncated fraction is
reported as a warning — never silently (AXIOMS §4 spirit).

Primary analysis: cluster-level change scores (post - pre proportions) compared between
arms with the pooled t-test — the analysis the §15.1 formula assumes — plus a
follow-up-only t-test to show the precision gained from baseline observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import stats

from icebergsim._version import SPEC_VERSION
from icebergsim.cluster import (
    _cluster_sizes,
    cluster_level_t_test,
    validate_cluster_trial,
)
from icebergsim.model import (
    ClusterPrePostSummary,
    ClusterPrePostTrialDefinition,
    ClusterTrialDefinition,
    ValidationError,
)
from icebergsim.model import (
    validation_error as _error,
)
from icebergsim.rng import RNG_ALGORITHM, create_rng
from icebergsim.simulate import input_hash

Errors = tuple[ValidationError, ...]
FloatArray = npt.NDArray[np.float64]

# Designs whose Gaussian latent-rate mass outside [0, 1] exceeds this are rejected at
# validation: beyond it, clipping materially biases realized means and effect sizes
# (AXIOMS §4: reject inconsistent scenarios rather than silently distort them).
MAX_EXPECTED_TRUNCATION = 0.05

NOTES = (
    "primary analysis: cluster-level change-score (post - pre) pooled t-test with "
    "df = k_control + k_intervention - 2, matching the SPEC §15.1 formula",
    "follow-up-only cluster-level t-test shown for comparison with the post-only design",
    "DiD sign convention: control change - intervention change; positive = benefit, "
    "matching ARR",
)


def validate_cluster_pre_post_trial(
    raw: Mapping[str, Any],
) -> ClusterPrePostTrialDefinition | Errors:
    """Validate a raw cluster_pre_post mapping.

    The cluster core (counts, sizes, ICC, arms, alpha, simulations) shares the
    cluster_post validator; this adds the pre/post correlation and the baseline rate.
    """
    errors: list[ValidationError] = []
    if not isinstance(raw, Mapping):
        return (_error("invalid_type", "Trial definition must be a mapping.", ""),)
    if raw.get("mode") != "cluster_pre_post":
        errors.append(
            _error(
                "invalid_mode",
                f"pre/post cluster trials require mode 'cluster_pre_post', "
                f"got {raw.get('mode')!r}.",
                "mode",
            )
        )
    core = validate_cluster_trial({**raw, "mode": "cluster_post"})
    if isinstance(core, tuple):
        errors.extend(core)

    correlation = raw.get("pre_post_correlation")
    if (
        isinstance(correlation, bool)
        or not isinstance(correlation, int | float)
        or not 0.0 <= float(correlation) <= 1.0
    ):
        errors.append(
            _error(
                "correlation_out_of_bounds",
                "pre_post_correlation must be a number in [0, 1].",
                "pre_post_correlation",
            )
        )
        correlation = 0.0

    baseline = raw.get("baseline_event_probability")
    if baseline is not None and (
        isinstance(baseline, bool)
        or not isinstance(baseline, int | float)
        or not 0.0 <= float(baseline) <= 1.0
    ):
        errors.append(
            _error(
                "probability_out_of_bounds",
                "baseline_event_probability must be a number in [0, 1].",
                "baseline_event_probability",
            )
        )
        baseline = None

    if not errors:
        assert isinstance(core, ClusterTrialDefinition)
        baseline_value = float(baseline) if baseline is not None else core.p_control
        for path, mu in (
            ("baseline_event_probability", baseline_value),
            ("arms.control.event_probability", core.p_control),
            ("arms.intervention.event_probability", core.p_intervention),
        ):
            mass = _expected_truncation(mu, core.icc)
            if mass > MAX_EXPECTED_TRUNCATION:
                errors.append(
                    _error(
                        "cluster_rate_truncation_excessive",
                        f"With ICC {core.icc:g} the Gaussian cluster-rate model around "
                        f"{path} = {mu:g} would truncate {mass:.1%} of latent rates, "
                        "materially biasing realized means and effect sizes. Reduce the "
                        "ICC or move the rate away from the [0, 1] boundary.",
                        path,
                        details={"expected_truncated_fraction": mass},
                    )
                )

    if errors:
        return tuple(errors)
    assert isinstance(core, ClusterTrialDefinition)
    return ClusterPrePostTrialDefinition(
        id=core.id,
        label=core.label,
        n_simulations=core.n_simulations,
        control_clusters=core.control_clusters,
        intervention_clusters=core.intervention_clusters,
        mean_cluster_size=core.mean_cluster_size,
        icc=core.icc,
        pre_post_correlation=float(correlation),
        # Randomization at baseline: default the shared pre-period rate to the control rate.
        baseline_event_probability=(
            float(baseline) if baseline is not None else core.p_control
        ),
        p_control=core.p_control,
        p_intervention=core.p_intervention,
        random_seed=core.random_seed,
        alpha=core.alpha,
        size_distribution=core.size_distribution,
    )


# --- simulation ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClusterPrePostArrays:
    """Per-replicate cluster proportions and analysis arrays. Read-only."""

    control_pre_proportions: FloatArray  # (n_sims, k_control)
    control_post_proportions: FloatArray
    intervention_pre_proportions: FloatArray  # (n_sims, k_intervention)
    intervention_post_proportions: FloatArray
    did: FloatArray  # (n_sims,) control change - intervention change
    did_ci_low: FloatArray
    did_ci_high: FloatArray
    p_change_score: FloatArray
    p_followup_only: FloatArray


@dataclass(frozen=True, slots=True)
class ClusterPrePostResult:
    """Pre/post cluster simulation with manifest (AXIOMS §3)."""

    input_hash: str
    random_seed: int | None
    n_simulations: int
    rng_algorithm: str
    spec_version: str
    definition: ClusterPrePostTrialDefinition
    arrays: ClusterPrePostArrays
    summary: ClusterPrePostSummary
    warnings: tuple[str, ...]
    notes: tuple[str, ...]


def simulate_cluster_pre_post(
    definition: ClusterPrePostTrialDefinition,
) -> ClusterPrePostResult:
    """Simulate correlated pre/post cluster observations and run both analyses."""
    rng = create_rng(definition.random_seed, "cluster_pre_post")
    control = _simulate_arm(definition, definition.control_clusters, definition.p_control, rng)
    intervention = _simulate_arm(
        definition, definition.intervention_clusters, definition.p_intervention, rng
    )
    control_pre, control_post, control_truncated = control
    intervention_pre, intervention_post, intervention_truncated = intervention

    control_change = control_post - control_pre
    intervention_change = intervention_post - intervention_pre
    did, did_ci_low, did_ci_high, p_change = cluster_level_t_test(
        control_change, intervention_change, definition.alpha
    )
    _, _, _, p_followup = cluster_level_t_test(
        control_post, intervention_post, definition.alpha
    )

    total_latent_draws = 2 * definition.n_simulations * (
        definition.control_clusters + definition.intervention_clusters
    )
    truncated_fraction = (control_truncated + intervention_truncated) / total_latent_draws
    warnings: tuple[str, ...] = ()
    if truncated_fraction > 0.0:
        warnings = (
            f"latent_rates_truncated:{truncated_fraction:.4f} (cluster rates clipped to "
            "[0, 1]; realized means and effect sizes are pulled toward the interior and "
            "between-cluster variance sits below the ICC target — the summary reports "
            "realized values)",
        )

    summary = ClusterPrePostSummary(
        mean_baseline_cer=float(control_pre.mean()),
        mean_baseline_eer=float(intervention_pre.mean()),
        mean_followup_cer=float(control_post.mean()),
        mean_followup_eer=float(intervention_post.mean()),
        mean_did=float(did.mean()),
        power_change_score=float(np.mean(p_change < definition.alpha)),
        power_followup_only=float(np.mean(p_followup < definition.alpha)),
        truncated_rate_fraction=float(truncated_fraction),
    )
    return ClusterPrePostResult(
        input_hash=input_hash(definition),
        random_seed=definition.random_seed,
        n_simulations=definition.n_simulations,
        rng_algorithm=RNG_ALGORITHM,
        spec_version=SPEC_VERSION,
        definition=definition,
        arrays=ClusterPrePostArrays(
            control_pre_proportions=_read_only(control_pre),
            control_post_proportions=_read_only(control_post),
            intervention_pre_proportions=_read_only(intervention_pre),
            intervention_post_proportions=_read_only(intervention_post),
            did=_read_only(did),
            did_ci_low=_read_only(did_ci_low),
            did_ci_high=_read_only(did_ci_high),
            p_change_score=_read_only(p_change),
            p_followup_only=_read_only(p_followup),
        ),
        summary=summary,
        warnings=warnings,
        notes=NOTES,
    )


def _simulate_arm(
    definition: ClusterPrePostTrialDefinition,
    n_clusters: int,
    followup_p: float,
    rng: np.random.Generator,
) -> tuple[FloatArray, FloatArray, int]:
    """One arm's (pre proportions, post proportions, truncated latent count)."""
    shape = (definition.n_simulations, n_clusters)
    sizes = _cluster_sizes(
        definition.size_distribution, definition.mean_cluster_size,
        n_clusters, definition.n_simulations, rng,
    )
    # Persistent (u) and period-specific (e) cluster effects give Corr(pre, post) = corr.
    corr = definition.pre_post_correlation
    persistent = rng.standard_normal(shape)
    weight_shared, weight_period = np.sqrt(corr), np.sqrt(1.0 - corr)

    def latent_rates(mu: float) -> tuple[FloatArray, int]:
        sd = float(np.sqrt(definition.icc * mu * (1.0 - mu)))
        z = weight_shared * persistent + weight_period * rng.standard_normal(shape)
        raw = mu + sd * z
        truncated = int(np.sum((raw < 0.0) | (raw > 1.0)))
        return np.clip(raw, 0.0, 1.0), truncated

    pre_rates, pre_truncated = latent_rates(definition.baseline_event_probability)
    post_rates, post_truncated = latent_rates(followup_p)
    pre_events = rng.binomial(sizes, pre_rates)
    post_events = rng.binomial(sizes, post_rates)
    return (
        pre_events / sizes,
        post_events / sizes,
        pre_truncated + post_truncated,
    )


def _read_only(array: FloatArray) -> FloatArray:
    array.setflags(write=False)
    return array


def _expected_truncation(mu: float, icc: float) -> float:
    """Gaussian mass of the latent-rate distribution outside [0, 1]."""
    sd = float(np.sqrt(icc * mu * (1.0 - mu)))
    if sd == 0.0:
        return 0.0
    below = float(stats.norm.cdf((0.0 - mu) / sd))
    above = float(stats.norm.sf((1.0 - mu) / sd))
    return below + above
