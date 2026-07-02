"""Post-only cluster randomized trial engine (SPEC §14, AXIOMS §11).

Cluster-level event probabilities are drawn from the beta-binomial model of §14.3. Three
analyses are always produced and labeled (§14.4):

1. unadjusted individual Pearson chi-square — anti-conservative under clustering;
2. cluster-level difference in means — pooled two-sample t-test on cluster proportions;
3. design-effect adjusted chi-square — Pearson X^2 divided by 1 + (m - 1) * ICC with m the
   realized mean cluster size of the replicate (effective-sample-size adjustment).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from scipy import stats

from icebergsim._version import SPEC_VERSION
from icebergsim.analysis import analyze_2x2_batch, batch_pearson_statistic
from icebergsim.model import (
    ClusterSimulationSummary,
    ClusterSizeDistribution,
    ClusterSizeType,
    ClusterTrialDefinition,
    ValidationError,
    round_half_up,
)
from icebergsim.model import (
    validation_error as _error,
)
from icebergsim.rng import RNG_ALGORITHM, create_rng
from icebergsim.simulate import SimulatedTables, input_hash

Errors = tuple[ValidationError, ...]
IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

CLUSTER_SIZE_TYPES = ("fixed", "poisson", "negative_binomial", "lognormal", "legacy_beta_size")
SUPPORTED_CLUSTER_SIZE_TYPES = ("fixed", "poisson", "negative_binomial", "lognormal")

NOTES = (
    "unadjusted_chi_square analyzes cluster-correlated individuals as independent and is "
    "anti-conservative (AXIOMS §11)",
    "adjusted_chi_square divides the Pearson statistic by the design effect "
    "1 + (m - 1) * ICC using the realized mean cluster size (SPEC §14.4)",
    "cluster_level_difference uses a pooled two-sample t-test on cluster event proportions "
    "with df = k_control + k_intervention - 2 (SPEC §14.4)",
)


def beta_binomial_parameters(p: float, icc: float) -> tuple[float, float] | Errors:
    """Beta parameters for the cluster event-rate distribution (SPEC §14.3).

        alpha = p * (1/ICC - 1),  beta = (1 - p) * (1/ICC - 1)

    Defined only for 0 < p < 1 and 0 < ICC < 1; ICC = 0 is handled by the engine as the
    degenerate constant-rate case.
    """
    errors: list[ValidationError] = []
    if not 0.0 < p < 1.0:
        errors.append(
            _error(
                "probability_out_of_bounds",
                "beta-binomial parameters require 0 < p < 1.",
                "arms.event_probability",
            )
        )
    if not 0.0 < icc < 1.0:
        errors.append(
            _error(
                "icc_out_of_bounds",
                "beta-binomial parameters require 0 < ICC < 1.",
                "icc",
            )
        )
    if errors:
        return tuple(errors)
    concentration = 1.0 / icc - 1.0
    return p * concentration, (1.0 - p) * concentration


# --- validation (SPEC §14.1) ----------------------------------------------------------------


def validate_cluster_trial(raw: Mapping[str, Any]) -> ClusterTrialDefinition | Errors:
    """Validate a raw cluster_post trial mapping into a ClusterTrialDefinition."""
    errors: list[ValidationError] = []
    if not isinstance(raw, Mapping):
        return (_error("invalid_type", "Cluster trial definition must be a mapping.", ""),)
    if raw.get("mode") != "cluster_post":
        errors.append(
            _error(
                "invalid_mode",
                f"cluster trials require mode 'cluster_post', got {raw.get('mode')!r}.",
                "mode",
            )
        )
    p_control = _probability(raw, ("arms", "control", "event_probability"), errors)
    p_intervention = _probability(raw, ("arms", "intervention", "event_probability"), errors)
    icc = raw.get("icc")
    if not _is_number(icc) or not 0.0 <= float(cast("float", icc)) < 1.0:
        errors.append(
            _error("icc_out_of_bounds", "icc must be a number in [0, 1).", "icc")
        )
        icc = 0.0
    n_simulations = raw.get("n_simulations")
    if not isinstance(n_simulations, int) or isinstance(n_simulations, bool) or n_simulations < 1:
        errors.append(
            _error(
                "sample_size_not_positive",
                "n_simulations must be a positive integer.",
                "n_simulations",
            )
        )
        n_simulations = 0
    alpha = raw.get("alpha", 0.05)
    if not _is_number(alpha) or not 0.0 < float(alpha) < 1.0:
        errors.append(
            _error("alpha_out_of_bounds", "alpha must be strictly between 0 and 1.", "alpha")
        )
        alpha = 0.05
    random_seed = raw.get("random_seed")
    if random_seed is not None and (
        isinstance(random_seed, bool) or not isinstance(random_seed, int)
    ):
        errors.append(_error("invalid_type", "random_seed must be an integer or null.",
                             "random_seed"))
        random_seed = None

    clusters = raw.get("clusters")
    if not isinstance(clusters, Mapping):
        errors.append(_error("missing_field", "clusters block is required.", "clusters"))
        return tuple(errors)
    control_clusters = clusters.get("control_clusters")
    intervention_clusters = clusters.get("intervention_clusters")
    for name, value in (
        ("control_clusters", control_clusters),
        ("intervention_clusters", intervention_clusters),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 2:
            errors.append(
                _error(
                    "cluster_count_too_small",
                    f"clusters.{name} must be an integer >= 2 (cluster-level analysis "
                    "needs at least two clusters per arm).",
                    f"clusters.{name}",
                )
            )
    mean_cluster_size = clusters.get("mean_cluster_size")
    if not _is_number(mean_cluster_size) or float(cast("float", mean_cluster_size)) < 1.0:
        errors.append(
            _error(
                "cluster_size_not_positive",
                "clusters.mean_cluster_size must be a number >= 1.",
                "clusters.mean_cluster_size",
            )
        )
        mean_cluster_size = 1.0
    size_distribution = _parse_size_distribution(
        clusters.get("cluster_size_distribution"), float(cast("float", mean_cluster_size)), errors
    )
    if errors:
        return tuple(errors)
    return ClusterTrialDefinition(
        id=str(raw.get("id", "")),
        label=str(raw.get("label", raw.get("id", ""))),
        n_simulations=int(n_simulations),
        control_clusters=int(cast("int", control_clusters)),
        intervention_clusters=int(cast("int", intervention_clusters)),
        mean_cluster_size=float(cast("float", mean_cluster_size)),
        icc=float(cast("float", icc)),
        p_control=p_control,
        p_intervention=p_intervention,
        random_seed=random_seed,
        alpha=float(alpha),
        size_distribution=size_distribution,
    )


def _parse_size_distribution(
    raw_dist: Any, mean_cluster_size: float, errors: list[ValidationError]
) -> ClusterSizeDistribution:
    if raw_dist is None:
        return ClusterSizeDistribution()
    if not isinstance(raw_dist, Mapping):
        errors.append(
            _error(
                "invalid_type",
                "clusters.cluster_size_distribution must be a mapping.",
                "clusters.cluster_size_distribution",
            )
        )
        return ClusterSizeDistribution()
    path = "clusters.cluster_size_distribution"
    dist_type = raw_dist.get("type", "fixed")
    if dist_type not in CLUSTER_SIZE_TYPES:
        errors.append(
            _error(
                "invalid_cluster_size_distribution",
                f"type must be one of {CLUSTER_SIZE_TYPES}, got {dist_type!r}.",
                f"{path}.type",
            )
        )
        dist_type = "fixed"
    elif dist_type not in SUPPORTED_CLUSTER_SIZE_TYPES:
        errors.append(
            _error(
                "cluster_size_distribution_not_supported",
                f"type {dist_type!r} is not supported by this implementation; "
                f"supported: {SUPPORTED_CLUSTER_SIZE_TYPES}.",
                f"{path}.type",
            )
        )
        dist_type = "fixed"
    sd = raw_dist.get("sd")
    if sd is not None and (not _is_number(sd) or float(sd) <= 0.0):
        errors.append(_error("invalid_type", f"{path}.sd must be a positive number or null.",
                             f"{path}.sd"))
        sd = None
    if dist_type in ("negative_binomial", "lognormal") and sd is None:
        errors.append(
            _error(
                "cluster_size_sd_required",
                f"{dist_type} cluster sizes require a positive sd.",
                f"{path}.sd",
            )
        )
    if dist_type == "negative_binomial" and sd is not None and float(sd) ** 2 <= mean_cluster_size:
        errors.append(
            _error(
                "cluster_size_sd_too_small",
                "negative_binomial requires sd^2 > mean_cluster_size (overdispersion).",
                f"{path}.sd",
            )
        )
    minimum = raw_dist.get("min", 1)
    maximum = raw_dist.get("max")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        errors.append(_error("invalid_type", f"{path}.min must be an integer >= 1.",
                             f"{path}.min"))
        minimum = 1
    if maximum is not None and (
        not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum
    ):
        errors.append(_error("invalid_type", f"{path}.max must be an integer >= min or null.",
                             f"{path}.max"))
        maximum = None
    return ClusterSizeDistribution(
        type=cast("ClusterSizeType", dist_type),
        sd=float(sd) if sd is not None else None,
        min=minimum,
        max=maximum,
    )


# --- simulation (SPEC §14.3-§14.4) -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClusterAnalysisArrays:
    """Per-replicate results of the three required analyses. Arrays are read-only."""

    p_unadjusted: FloatArray
    p_adjusted: FloatArray
    p_cluster_level: FloatArray
    cluster_level_difference: FloatArray
    cluster_level_ci_low: FloatArray
    cluster_level_ci_high: FloatArray
    design_effect: FloatArray


@dataclass(frozen=True, slots=True)
class ClusterSimulationResult:
    """Cluster simulation with pooled tables, three analyses, and manifest (AXIOMS §3)."""

    input_hash: str
    random_seed: int | None
    n_simulations: int
    rng_algorithm: str
    spec_version: str
    definition: ClusterTrialDefinition
    tables: SimulatedTables
    arrays: ClusterAnalysisArrays
    summary: ClusterSimulationSummary
    notes: tuple[str, ...]


def simulate_cluster_post_only(definition: ClusterTrialDefinition) -> ClusterSimulationResult:
    """Simulate a post-only cluster randomized trial (SPEC §14.3) and run all analyses."""
    rng = create_rng(definition.random_seed, "cluster")
    n_sims = definition.n_simulations
    control = _simulate_cluster_arm(
        definition, definition.control_clusters, definition.p_control, n_sims, rng
    )
    intervention = _simulate_cluster_arm(
        definition, definition.intervention_clusters, definition.p_intervention, n_sims, rng
    )
    control_events, control_sizes = control
    intervention_events, intervention_sizes = intervention

    tables = SimulatedTables(
        control_events=_read_only(control_events.sum(axis=1)),
        control_observed=_read_only(control_sizes.sum(axis=1)),
        intervention_events=_read_only(intervention_events.sum(axis=1)),
        intervention_observed=_read_only(intervention_sizes.sum(axis=1)),
    )
    pooled = analyze_2x2_batch(
        control_events=tables.control_events,
        control_observed=tables.control_observed,
        intervention_events=tables.intervention_events,
        intervention_observed=tables.intervention_observed,
        p_value_method="pearson_chi_square",
    )
    statistic = batch_pearson_statistic(
        tables.control_events,
        tables.control_observed,
        tables.intervention_events,
        tables.intervention_observed,
    )
    total_clusters = definition.control_clusters + definition.intervention_clusters
    realized_mean_size = (
        np.asarray(tables.control_observed + tables.intervention_observed, dtype=np.float64)
        / total_clusters
    )
    design_effect = 1.0 + (realized_mean_size - 1.0) * definition.icc
    p_adjusted = np.asarray(stats.chi2.sf(statistic / design_effect, df=1), dtype=np.float64)

    difference, ci_low, ci_high, p_cluster = _cluster_level_difference(
        control_events, control_sizes, intervention_events, intervention_sizes,
        definition.alpha,
    )
    arrays = ClusterAnalysisArrays(
        p_unadjusted=pooled.p_values,
        p_adjusted=_read_only(p_adjusted),
        p_cluster_level=_read_only(p_cluster),
        cluster_level_difference=_read_only(difference),
        cluster_level_ci_low=_read_only(ci_low),
        cluster_level_ci_high=_read_only(ci_high),
        design_effect=_read_only(design_effect),
    )
    alpha = definition.alpha
    with np.errstate(invalid="ignore"):
        summary = ClusterSimulationSummary(
            mean_cer=float(pooled.cer.mean()),
            mean_eer=float(pooled.eer.mean()),
            mean_design_effect=float(design_effect.mean()),
            mean_cluster_level_difference=float(difference.mean()),
            power_unadjusted_chi_square=float(np.mean(arrays.p_unadjusted < alpha)),
            power_adjusted_chi_square=float(np.mean(arrays.p_adjusted < alpha)),
            power_cluster_level_difference=float(np.mean(arrays.p_cluster_level < alpha)),
        )
    return ClusterSimulationResult(
        input_hash=input_hash(definition),
        random_seed=definition.random_seed,
        n_simulations=n_sims,
        rng_algorithm=RNG_ALGORITHM,
        spec_version=SPEC_VERSION,
        definition=definition,
        tables=tables,
        arrays=arrays,
        summary=summary,
        notes=NOTES,
    )


def _simulate_cluster_arm(
    definition: ClusterTrialDefinition,
    n_clusters: int,
    p: float,
    n_sims: int,
    rng: np.random.Generator,
) -> tuple[IntArray, IntArray]:
    """Per-cluster (events, sizes) arrays of shape (n_sims, n_clusters) per SPEC §14.3."""
    sizes = _cluster_sizes(definition.size_distribution, definition.mean_cluster_size,
                           n_clusters, n_sims, rng)
    if definition.icc == 0.0 or p in (0.0, 1.0):
        # Degenerate cases: every cluster shares the arm rate exactly.
        cluster_p: FloatArray | float = p
    else:
        parameters = beta_binomial_parameters(p, definition.icc)
        assert not isinstance(parameters[0], ValidationError)  # validated inputs
        alpha_beta, beta_beta = parameters
        cluster_p = rng.beta(alpha_beta, beta_beta, size=(n_sims, n_clusters))
    events = rng.binomial(sizes, cluster_p)
    return events.astype(np.int64), sizes


def _cluster_sizes(
    distribution: ClusterSizeDistribution,
    mean_size: float,
    n_clusters: int,
    n_sims: int,
    rng: np.random.Generator,
) -> IntArray:
    shape = (n_sims, n_clusters)
    if distribution.type == "fixed":
        sizes = np.full(shape, round_half_up(mean_size), dtype=np.int64)
    elif distribution.type == "poisson":
        sizes = rng.poisson(mean_size, size=shape).astype(np.int64)
    elif distribution.type == "negative_binomial":
        assert distribution.sd is not None  # enforced by validation
        variance = distribution.sd**2
        shape_k = mean_size**2 / (variance - mean_size)
        sizes = rng.negative_binomial(shape_k, shape_k / (shape_k + mean_size),
                                      size=shape).astype(np.int64)
    else:  # lognormal
        assert distribution.sd is not None  # enforced by validation
        sigma_sq = np.log(1.0 + (distribution.sd / mean_size) ** 2)
        mu = np.log(mean_size) - sigma_sq / 2.0
        sizes = np.floor(rng.lognormal(mu, np.sqrt(sigma_sq), size=shape) + 0.5).astype(np.int64)
    maximum = distribution.max if distribution.max is not None else np.iinfo(np.int64).max
    return np.clip(sizes, distribution.min, maximum)


def _cluster_level_difference(
    control_events: IntArray,
    control_sizes: IntArray,
    intervention_events: IntArray,
    intervention_sizes: IntArray,
    alpha: float,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Pooled two-sample t-test on cluster event proportions (SPEC §14.4)."""
    control_props = control_events / control_sizes
    intervention_props = intervention_events / intervention_sizes
    k_control, k_intervention = control_props.shape[1], intervention_props.shape[1]
    difference = control_props.mean(axis=1) - intervention_props.mean(axis=1)
    df = k_control + k_intervention - 2
    pooled_variance = (
        (k_control - 1) * control_props.var(axis=1, ddof=1)
        + (k_intervention - 1) * intervention_props.var(axis=1, ddof=1)
    ) / df
    standard_error = np.sqrt(pooled_variance * (1.0 / k_control + 1.0 / k_intervention))
    # Zero standard error (all cluster proportions identical): t is 0 when the arms agree
    # exactly and +/-inf otherwise, giving p = 1 and p = 0 respectively.
    degenerate = np.where(difference > 0.0, np.inf, np.where(difference < 0.0, -np.inf, 0.0))
    t_statistic = np.where(
        standard_error > 0.0,
        difference / np.where(standard_error > 0.0, standard_error, 1.0),
        degenerate,
    )
    p_values = np.asarray(2.0 * stats.t.sf(np.abs(t_statistic), df=df), dtype=np.float64)
    t_critical = float(stats.t.ppf(1.0 - alpha / 2.0, df=df))
    ci_low = difference - t_critical * standard_error
    ci_high = difference + t_critical * standard_error
    return difference, ci_low, ci_high, p_values


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _probability(
    raw: Mapping[str, Any], keys: tuple[str, ...], errors: list[ValidationError]
) -> float:
    node: Any = raw
    for key in keys:
        node = node.get(key) if isinstance(node, Mapping) else None
    path = ".".join(keys)
    if not _is_number(node) or not 0.0 <= float(node) <= 1.0:
        errors.append(
            _error("probability_out_of_bounds", f"{path} must be a number in [0, 1].", path)
        )
        return 0.0
    return float(node)


def _read_only[ArrayT: np.generic](array: npt.NDArray[ArrayT]) -> npt.NDArray[ArrayT]:
    array.setflags(write=False)
    return array
