"""Registry mapping spec/tests.yaml (module, function) pairs to implementation adapters.

Each adapter is a thin, logic-free bridge: it unpacks the case's ``input`` mapping, calls the
real icebergsim function, and repacks the result under the keys the spec expects. Statistical
logic belongs in src/icebergsim/, never here.

Adapters are registered step by step as modules are implemented; cases without an adapter
are reported as xfail by tests/test_spec_yaml.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import numpy as np

from icebergsim.analysis import analyze_2x2
from icebergsim.analysis import analyze_2x2 as _analyze
from icebergsim.cluster import beta_binomial_parameters
from icebergsim.model import Table2x2, ValidationError
from icebergsim.sample_size import (
    calculate_cluster_post_sample_size,
    calculate_two_arm_sample_size,
)
from icebergsim.simulate import SimulationResult, simulate_trial
from icebergsim.stopping import make_stopping_plan
from icebergsim.subgroups import aggregate_subgroup_tables
from icebergsim.validate import derive_loss_probabilities, validate_trial_definition
from spec_harness import Adapter


def _error_payload(errors: tuple[ValidationError, ...]) -> dict[str, Any]:
    first = errors[0]
    return {
        "error": {
            "type": first.type,
            "code": first.code,
            "message": first.message,
            "path": first.path,
            "details": dict(first.details),
        }
    }


def _adapt_loss_adjustment(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    result = derive_loss_probabilities(
        p_exposure=case_input["p_exposure"],
        loss_probability=case_input["loss_probability"],
        lost_event_risk_ratio=case_input["lost_event_risk_ratio"],
    )
    if isinstance(result, tuple):
        return _error_payload(result)
    return {"p_lost": result.p_lost, "p_nonlost": result.p_nonlost}


def _adapt_validate_trial_definition(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    result = validate_trial_definition(case_input)
    if isinstance(result, tuple):
        return _error_payload(result)
    return {
        "valid": True,
        "n_control": result.n_control,
        "n_intervention": result.n_intervention,
    }


def _adapt_analyze_2x2(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    # Distinguish "explicitly null" from "absent" for the zero-cell correction (SPEC §7.4).
    correction = case_input.get("zero_cell_correction", 0.5)
    result = analyze_2x2(
        Table2x2(
            control_events=case_input["control_events"],
            control_observed=case_input["control_observed"],
            intervention_events=case_input["intervention_events"],
            intervention_observed=case_input["intervention_observed"],
        ),
        alpha=case_input.get("alpha", 0.05),
        zero_cell_correction=correction,
    )
    return {
        "cer": result.cer,
        "eer": result.eer,
        "arr": result.arr,
        "rr": result.rr,
        "rrr": result.rrr,
        "nnt": result.nnt,
        "nnh": result.nnh,
        "p_value": result.p_value,
        "warnings": list(result.warnings),
    }


def _adapt_two_arm_sample_size(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    result = calculate_two_arm_sample_size(
        p_control=case_input["p_control"],
        p_intervention=case_input["p_intervention"],
        alpha=case_input.get("alpha", 0.05),
        power=case_input.get("power", 0.80),
        alternative=case_input.get("alternative", "two_sided"),
        allocation_ratio_intervention_to_control=case_input.get(
            "allocation_ratio_intervention_to_control", 1.0
        ),
    )
    if isinstance(result, tuple):
        return _error_payload(result)
    out: dict[str, Any] = {
        "n_control": result.n_control,
        "n_intervention": result.n_intervention,
        "n_total": result.n_total,
    }
    if result.allocation_ratio_intervention_to_control == 1.0:
        out["unrounded_n_per_arm"] = result.unrounded_n_control
    return out


def _adapt_cluster_post_sample_size(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    result = calculate_cluster_post_sample_size(
        p_control=case_input["p_control"],
        p_intervention=case_input["p_intervention"],
        alpha=case_input.get("alpha", 0.05),
        power=case_input.get("power", 0.80),
        alternative=case_input.get("alternative", "two_sided"),
        mean_cluster_size=case_input["mean_cluster_size"],
        icc=case_input["icc"],
    )
    if isinstance(result, tuple):
        return _error_payload(result)
    return {
        "individual_n_per_arm_unrounded": result.individual_n_per_arm_unrounded,
        "design_effect": result.design_effect,
        "cluster_adjusted_n_per_arm_unrounded": result.cluster_adjusted_n_per_arm_unrounded,
        "clusters_per_arm": result.clusters_per_arm,
    }


def _run_simulation(raw: Mapping[str, Any]) -> SimulationResult:
    validated = validate_trial_definition(raw)
    assert not isinstance(validated, tuple), f"case input failed validation: {validated}"
    return simulate_trial(validated)


def _adapt_simulate_individual_trial(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    if "run_a" in case_input:  # seed_reproducibility: same definition simulated twice
        a = _run_simulation(case_input["run_a"])
        b = _run_simulation(case_input["run_a"])
        identical = (
            np.array_equal(a.tables.control_events, b.tables.control_events)
            and np.array_equal(a.tables.control_observed, b.tables.control_observed)
            and np.array_equal(a.tables.intervention_events, b.tables.intervention_events)
            and np.array_equal(a.tables.intervention_observed, b.tables.intervention_observed)
            and np.array_equal(a.arrays.p_values, b.arrays.p_values)
        )
        return {"arrays_identical": identical}
    if "pragmatic" in case_input:  # ideal-vs-pragmatic power comparison
        ideal = _run_simulation(case_input["ideal"])
        worse = _run_simulation(case_input["pragmatic"])
        return {
            "pragmatic_power_less_than_ideal_power": worse.summary.power
            < ideal.summary.power
        }
    result = _run_simulation(case_input)
    return {
        "mean_cer": result.summary.mean_cer,
        "mean_eer": result.summary.mean_eer,
        "power": result.summary.power,
    }


def _adapt_make_stopping_plan(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    interims = case_input.get("interim_p_thresholds")
    fractions = case_input.get("information_fractions")
    result = make_stopping_plan(
        rule=case_input["rule"],
        n_interims=case_input["n_interims"],
        information_fractions=tuple(fractions) if fractions is not None else None,
        interim_p_thresholds=tuple(interims) if interims is not None else None,
        final_p_threshold=case_input.get("final_p_threshold"),
    )
    if isinstance(result, tuple):
        return _error_payload(result)
    return {
        "interim_p_thresholds": list(result.interim_p_thresholds),
        "final_p_threshold": result.final_p_threshold,
        "information_fractions": list(result.information_fractions),
    }


def _adapt_aggregate_subgroup_tables(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    aggregate = aggregate_subgroup_tables(
        [
            Table2x2(
                control_events=t["control_events"],
                control_observed=t["control_observed"],
                intervention_events=t["intervention_events"],
                intervention_observed=t["intervention_observed"],
            )
            for t in case_input["subgroup_tables"]
        ]
    )
    analysis = _analyze(aggregate)
    return {
        "control_events": aggregate.control_events,
        "control_observed": aggregate.control_observed,
        "intervention_events": aggregate.intervention_events,
        "intervention_observed": aggregate.intervention_observed,
        "aggregate_cer": analysis.cer,
        "aggregate_eer": analysis.eer,
        "aggregate_arr": analysis.arr,
    }


def _adapt_beta_parameters(case_input: Mapping[str, Any]) -> Mapping[str, Any]:
    result = beta_binomial_parameters(case_input["p"], case_input["icc"])
    if result and isinstance(result[0], ValidationError):
        return _error_payload(result)
    alpha, beta = cast("tuple[float, float]", result)
    return {"alpha": alpha, "beta": beta}


ADAPTERS: dict[tuple[str, str], Adapter] = {
    ("stopping", "make_stopping_plan"): _adapt_make_stopping_plan,
    ("risk_subgroups", "aggregate_subgroup_tables"): _adapt_aggregate_subgroup_tables,
    ("cluster", "beta_parameters"): _adapt_beta_parameters,
    ("derived_probabilities", "loss_adjustment"): _adapt_loss_adjustment,
    ("individual_simulation", "validate_trial_definition"): _adapt_validate_trial_definition,
    ("individual_simulation", "simulate_individual_trial"): _adapt_simulate_individual_trial,
    ("analysis", "analyze_2x2"): _adapt_analyze_2x2,
    ("sample_size", "calculate_two_arm_sample_size"): _adapt_two_arm_sample_size,
    ("cluster", "sample_size_cluster_post"): _adapt_cluster_post_sample_size,
}
