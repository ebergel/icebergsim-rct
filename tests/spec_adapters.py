"""Registry mapping spec/tests.yaml (module, function) pairs to implementation adapters.

Each adapter is a thin, logic-free bridge: it unpacks the case's ``input`` mapping, calls the
real icebergsim function, and repacks the result under the keys the spec expects. Statistical
logic belongs in src/icebergsim/, never here.

Adapters are registered step by step as modules are implemented; cases without an adapter
are reported as xfail by tests/test_spec_yaml.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from icebergsim.analysis import analyze_2x2
from icebergsim.model import Table2x2, ValidationError
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


ADAPTERS: dict[tuple[str, str], Adapter] = {
    ("derived_probabilities", "loss_adjustment"): _adapt_loss_adjustment,
    ("individual_simulation", "validate_trial_definition"): _adapt_validate_trial_definition,
    ("analysis", "analyze_2x2"): _adapt_analyze_2x2,
}
