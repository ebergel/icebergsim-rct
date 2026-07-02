"""Shared builders for validated trial definitions used across test modules."""

from __future__ import annotations

from typing import Any

from icebergsim.model import ValidatedTrial
from icebergsim.validate import validate_trial_definition


def make_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "icebergsim.trial.v2",
        "id": "test_trial",
        "label": "Test trial",
        "mode": "individual_binary",
        "n_simulations": 2000,
        "random_seed": 12345,
        "alpha": 0.05,
        "arms": {
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.10},
        },
        "allocation": {"total_n": 400, "intervention_fraction": 0.5},
        "untreated_event_probability": 0.30,
    }
    raw.update(overrides)
    return raw


def make_validated(**overrides: Any) -> ValidatedTrial:
    result = validate_trial_definition(make_raw(**overrides))
    assert isinstance(result, ValidatedTrial), f"builder produced invalid trial: {result}"
    return result
