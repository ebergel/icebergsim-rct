"""ICEBERGSIM v2 — clinical trial simulator regenerated from the Phoenix specification.

The canonical service API (ARCHITECTURE §4) is re-exported here. All engine functions are
pure; validation returns structured errors as data; only icebergsim.io touches files.
"""

from icebergsim._version import SPEC_VERSION
from icebergsim.analysis import analyze_2x2, analyze_2x2_batch, summarize_batch
from icebergsim.cluster import (
    beta_binomial_parameters,
    simulate_cluster_post_only,
    validate_cluster_trial,
)
from icebergsim.sample_size import (
    calculate_cluster_post_sample_size,
    calculate_cluster_pre_post_sample_size,
    calculate_two_arm_sample_size,
)
from icebergsim.scenarios import scenario_summary_table, simulate_scenario_family
from icebergsim.simulate import (
    simulate_null,
    simulate_power_curve,
    simulate_trial,
)
from icebergsim.stopping import make_stopping_plan, simulate_with_stopping
from icebergsim.subgroups import (
    aggregate_subgroup_tables,
    simulate_risk_subgroups,
    validate_subgroup_family,
)
from icebergsim.validate import derive_loss_probabilities, validate_trial_definition

__all__ = [
    "SPEC_VERSION",
    "aggregate_subgroup_tables",
    "analyze_2x2",
    "analyze_2x2_batch",
    "beta_binomial_parameters",
    "calculate_cluster_post_sample_size",
    "calculate_cluster_pre_post_sample_size",
    "calculate_two_arm_sample_size",
    "derive_loss_probabilities",
    "make_stopping_plan",
    "scenario_summary_table",
    "simulate_cluster_post_only",
    "simulate_null",
    "simulate_power_curve",
    "simulate_risk_subgroups",
    "simulate_scenario_family",
    "simulate_trial",
    "simulate_with_stopping",
    "summarize_batch",
    "validate_cluster_trial",
    "validate_subgroup_family",
    "validate_trial_definition",
]
