"""End-to-end runs of the canonical example definitions in spec/examples/ (INSTALL.md §5)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from icebergsim.cluster import simulate_cluster_post_only, validate_cluster_trial
from icebergsim.io import load_definition
from icebergsim.model import ClusterTrialDefinition, StoppingPlan, ValidatedTrial
from icebergsim.simulate import simulate_trial
from icebergsim.stopping import simulate_with_stopping
from icebergsim.validate import validate_trial_definition

EXAMPLES = Path(__file__).resolve().parent.parent / "spec" / "examples"


def load_example(name: str) -> Any:
    return load_definition(EXAMPLES / name)


def test_simple_two_arm_example() -> None:
    validated = validate_trial_definition(load_example("simple_two_arm.yaml"))
    assert isinstance(validated, ValidatedTrial)
    assert validated.n_control == 200
    result = simulate_trial(validated, include_type_i_error=True)
    assert 0.75 <= result.summary.power <= 0.90
    assert result.summary.type_i_error is not None
    assert abs(result.summary.type_i_error - 0.05) < 0.02
    assert result.random_seed == 101


def test_pragmatic_example_loses_power_vs_ideal() -> None:
    ideal = validate_trial_definition(load_example("simple_two_arm.yaml"))
    pragmatic = validate_trial_definition(load_example("pragmatic_trial_with_loss.yaml"))
    assert isinstance(ideal, ValidatedTrial)
    assert isinstance(pragmatic, ValidatedTrial)
    assert pragmatic.definition.control_imperfections.lost_event_risk_ratio == 1.5
    ideal_result = simulate_trial(ideal)
    pragmatic_result = simulate_trial(pragmatic)
    assert pragmatic_result.summary.power < ideal_result.summary.power


def test_stopping_example() -> None:
    validated = validate_trial_definition(load_example("stopping_trial.yaml"))
    assert isinstance(validated, ValidatedTrial)
    plan = validated.definition.stopping
    assert isinstance(plan, StoppingPlan)
    assert plan.rule == "peto"
    assert plan.information_fractions == (0.25, 0.5, 0.75)
    assert plan.interim_p_thresholds == (0.001, 0.001, 0.001)
    result = simulate_with_stopping(validated)
    assert result.look_sample_sizes[-1] == (400, 400)  # total_n 800
    assert result.summary.final_power_including_stops > 0.9
    assert 0.0 <= result.summary.proportion_stopped_any <= 1.0


def test_cluster_example() -> None:
    definition = validate_cluster_trial(load_example("cluster_trial.yaml"))
    assert isinstance(definition, ClusterTrialDefinition)
    assert definition.control_clusters == 4
    assert definition.icc == 0.01
    result = simulate_cluster_post_only(definition)
    assert math.isclose(result.summary.mean_design_effect, 1.99, abs_tol=1e-9)
    assert math.isclose(result.summary.mean_cer, 0.20, abs_tol=0.015)
    assert 0.4 <= result.summary.power_adjusted_chi_square <= 0.95
    assert any("anti-conservative" in note for note in result.notes)
