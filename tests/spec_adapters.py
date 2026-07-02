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

from icebergsim.model import ValidationError
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


ADAPTERS: dict[tuple[str, str], Adapter] = {
    ("derived_probabilities", "loss_adjustment"): _adapt_loss_adjustment,
    ("individual_simulation", "validate_trial_definition"): _adapt_validate_trial_definition,
}
