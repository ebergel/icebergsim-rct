"""Immutable domain model (SPEC §4, ARCHITECTURE §3.1).

All objects are frozen dataclasses with spec defaults. They carry data only — behavior lives
in pure functions in the engine modules. Collections inside domain objects are tuples.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Mode = Literal["individual_binary", "cluster_post", "cluster_pre_post"]
Alternative = Literal["two_sided", "superiority_one_sided", "noninferiority_one_sided"]
PValueMethod = Literal[
    "likelihood_ratio", "pearson_chi_square", "fisher_exact", "monte_carlo_exact"
]
AnalysisPopulation = Literal[
    "intention_to_treat_observed",
    "intention_to_treat_all_randomized",
    "as_treated",
    "per_protocol",
]
StoppingRule = Literal["peto", "pocock", "obrien_fleming", "custom"]
StopFor = Literal["benefit", "harm", "benefit_or_harm"]


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Structured validation error (SPEC §18). Returned as data, never raised."""

    code: str
    message: str
    path: str
    type: str = "ValidationError"
    details: Mapping[str, Any] = field(default_factory=dict)


def validation_error(
    code: str, message: str, path: str, details: Mapping[str, Any] | None = None
) -> ValidationError:
    """Convenience constructor used by all validation stages."""
    return ValidationError(code=code, message=message, path=path, details=details or {})


@dataclass(frozen=True, slots=True)
class ImperfectionDefinition:
    """Per-assigned-arm trial imperfections with spec defaults (SPEC §4.2)."""

    loss_probability: float = 0.0
    lost_event_risk_ratio: float = 1.0
    noncompliance_probability: float = 0.0
    crossover_probability: float = 0.0
    ascertainment_event_probability: float = 1.0
    ascertainment_nonevent_false_positive_probability: float = 0.0


@dataclass(frozen=True, slots=True)
class ArmDefinition:
    event_probability: float
    label: str = ""
    n: int | None = None


@dataclass(frozen=True, slots=True)
class Allocation:
    total_n: int | None = None
    intervention_fraction: float = 0.5


@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    p_value_method: PValueMethod = "likelihood_ratio"
    confidence_interval_method: str = "log_rr_and_wald_arr"
    include_lost_in_denominator: bool = False
    analysis_population: AnalysisPopulation = "intention_to_treat_observed"


@dataclass(frozen=True, slots=True)
class StoppingPlan:
    """Interim stopping plan (SPEC §11.1). Data only; construction/validation in stopping.py."""

    rule: StoppingRule
    n_interims: int
    information_fractions: tuple[float, ...]
    interim_p_thresholds: tuple[float, ...]
    final_p_threshold: float
    enabled: bool = True
    stop_for: StopFor = "benefit_or_harm"
    minimum_total_events: int | None = None


@dataclass(frozen=True, slots=True)
class TrialDefinition:
    """A complete individually randomized trial definition (SPEC §4.1)."""

    id: str
    mode: Mode
    n_simulations: int
    control: ArmDefinition
    intervention: ArmDefinition
    untreated_event_probability: float
    schema_version: str = "icebergsim.trial.v2"
    label: str = ""
    random_seed: int | None = None
    alpha: float = 0.05
    alternative: Alternative = "two_sided"
    zero_cell_correction: float | None = 0.5
    allocation: Allocation = Allocation()
    control_imperfections: ImperfectionDefinition = ImperfectionDefinition()
    intervention_imperfections: ImperfectionDefinition = ImperfectionDefinition()
    analysis: AnalysisOptions = AnalysisOptions()
    stopping: StoppingPlan | None = None


@dataclass(frozen=True, slots=True)
class ValidatedTrial:
    """A trial definition that passed validation, with resolved per-arm sample sizes."""

    definition: TrialDefinition
    n_control: int
    n_intervention: int


@dataclass(frozen=True, slots=True)
class DerivedLossProbabilities:
    """Event probabilities for lost / non-lost participants (SPEC §5.3, AXIOMS §8)."""

    p_lost: float
    p_nonlost: float


@dataclass(frozen=True, slots=True)
class TwoArmSampleSizeResult:
    """Formula sample size for two independent proportions (SPEC §10)."""

    n_control: int
    n_intervention: int
    n_total: int
    unrounded_n_control: float
    unrounded_n_intervention: float
    allocation_ratio_intervention_to_control: float
    formula: str


@dataclass(frozen=True, slots=True)
class ClusterPostSampleSizeResult:
    """Design-effect adjusted sample size for post-only cluster trials (SPEC §14.2)."""

    individual_n_per_arm_unrounded: float
    design_effect: float
    cluster_adjusted_n_per_arm_unrounded: float
    n_per_arm_cluster_adjusted: int
    clusters_per_arm: int
    formula: str


@dataclass(frozen=True, slots=True)
class ClusterPrePostSampleSizeResult:
    """Pre/post cluster sample size using the historical formula (SPEC §15.1)."""

    n_per_arm_unrounded: float
    n_per_arm: int
    clusters_per_arm: int
    formula: str


@dataclass(frozen=True, slots=True)
class Table2x2:
    """Observed counts of one simulated trial: events and denominators by assigned arm."""

    control_events: int
    control_observed: int
    intervention_events: int
    intervention_observed: int


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Analysis of one 2x2 table (SPEC §7). Undefined quantities are None, with a warning."""

    cer: float | None
    eer: float | None
    arr: float | None
    rr: float | None
    rrr: float | None
    nnt: float | None
    nnh: float | None
    arr_ci: tuple[float, float] | None
    rr_ci: tuple[float, float] | None
    rrr_ci: tuple[float, float] | None
    p_value: float | None
    warnings: tuple[str, ...]
