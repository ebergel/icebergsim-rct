"""API routes: thin bridges from HTTP to the icebergsim domain services.

Error contract: any domain validation failure returns HTTP 422 with
``{"errors": [{type, code, message, path, details}, ...]}`` — the engine's own structured
errors, so clients can highlight the exact offending input field.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from icebergsim._version import SPEC_VERSION
from icebergsim.io import load_definition, result_to_dict
from icebergsim.model import ValidationError, validation_error
from icebergsim.plots import arr_histogram, power_curve_data, rr_vs_p_scatter
from icebergsim.rng import RNG_ALGORITHM
from icebergsim.sample_size import calculate_two_arm_sample_size
from icebergsim.simulate import (
    PowerCurveResult,
    SimulationResult,
    simulate_power_curve,
    simulate_trial,
)
from icebergsim.stopping import STOPPING_RULES
from icebergsim.validate import (
    SUPPORTED_ANALYSIS_POPULATIONS,
    SUPPORTED_P_VALUE_METHODS,
    validate_trial_definition,
)

Errors = tuple[ValidationError, ...]


def api_router(examples_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/meta")
    def meta() -> dict[str, Any]:
        return {
            "spec_version": SPEC_VERSION,
            "rng_algorithm": RNG_ALGORITHM,
            "p_value_methods": list(SUPPORTED_P_VALUE_METHODS),
            "analysis_populations": list(SUPPORTED_ANALYSIS_POPULATIONS),
            "stopping_rules": list(STOPPING_RULES),
            "export_formats": ["json", "yaml", "csv"],
            "modes": ["individual_binary", "cluster_post"],
        }

    @router.get("/examples")
    def examples() -> list[dict[str, Any]]:
        listed = []
        for path in sorted(examples_dir.glob("*.yaml")):
            raw = load_definition(path)
            listed.append(
                {
                    "name": path.stem,
                    "id": raw.get("id"),
                    "label": raw.get("label"),
                    "mode": raw.get("mode"),
                }
            )
        return listed

    @router.get("/examples/{name}")
    def example_detail(name: str) -> Any:
        # Resolve strictly against the known example files; no path components.
        known = {path.stem: path for path in examples_dir.glob("*.yaml")}
        if name not in known:
            raise HTTPException(status_code=404, detail=f"unknown example {name!r}")
        return load_definition(known[name])

    @router.post("/validate")
    def validate(definition: dict[str, Any]) -> Any:
        result = validate_trial_definition(definition)
        if isinstance(result, tuple):
            return _errors_response(result)
        return {
            "valid": True,
            "n_control": result.n_control,
            "n_intervention": result.n_intervention,
        }

    @router.post("/simulate")
    def simulate(
        definition: dict[str, Any],
        include_type_i_error: bool = Query(default=False),
        include_arrays: bool = Query(default=False),
    ) -> Any:
        validated = validate_trial_definition(definition)
        if isinstance(validated, tuple):
            return _errors_response(validated)
        result = simulate_trial(validated, include_type_i_error=include_type_i_error)
        return _simulation_payload(result, include_arrays=include_arrays)

    @router.post("/sample-size/two-arm")
    def sample_size_two_arm(params: dict[str, Any]) -> Any:
        numbers, errors = _read_numbers(
            params,
            required=("p_control", "p_intervention"),
            optional={
                "alpha": 0.05,
                "power": 0.80,
                "allocation_ratio_intervention_to_control": 1.0,
            },
        )
        if errors:
            return _errors_response(tuple(errors))
        result = calculate_two_arm_sample_size(
            alternative=str(params.get("alternative", "two_sided")), **numbers
        )
        if isinstance(result, tuple):
            return _errors_response(result)
        return dataclasses.asdict(result)

    @router.post("/power-curve")
    def power_curve(body: dict[str, Any]) -> Any:
        definition = body.get("definition")
        sizes = body.get("total_sample_sizes")
        errors = []
        if not isinstance(definition, dict):
            errors.append(
                validation_error("missing_field", "definition is required.", "definition")
            )
        if not isinstance(sizes, list):
            errors.append(
                validation_error(
                    "missing_field",
                    "total_sample_sizes must be a list of integers.",
                    "total_sample_sizes",
                )
            )
        if errors:
            return _errors_response(tuple(errors))
        validated = validate_trial_definition(definition)  # type: ignore[arg-type]
        if isinstance(validated, tuple):
            return _errors_response(validated)
        curve = simulate_power_curve(validated, sizes)  # type: ignore[arg-type]
        if not isinstance(curve, PowerCurveResult):
            return _errors_response(curve)
        payload = dataclasses.asdict(curve)
        payload["plot"] = dataclasses.asdict(power_curve_data(curve))
        return payload

    return router


def _read_numbers(
    params: dict[str, Any],
    *,
    required: tuple[str, ...],
    optional: dict[str, float],
) -> tuple[dict[str, float], list[ValidationError]]:
    """Type-check numeric request fields; parsing only, no statistics."""
    numbers: dict[str, float] = {}
    errors: list[ValidationError] = []
    for key in required:
        value = params.get(key)
        if value is None:
            errors.append(validation_error("missing_field", f"{key} is required.", key))
        elif isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(
                validation_error("invalid_type", f"{key} must be a number.", key)
            )
        else:
            numbers[key] = float(value)
    for key, default in optional.items():
        value = params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(validation_error("invalid_type", f"{key} must be a number.", key))
        else:
            numbers[key] = float(value)
    return numbers, errors


def _simulation_payload(result: SimulationResult, *, include_arrays: bool) -> dict[str, Any]:
    payload = result_to_dict(result, include_arrays=include_arrays)
    payload["plots"] = {
        "rr_vs_p": dataclasses.asdict(rr_vs_p_scatter(result)),
        "arr_histogram": dataclasses.asdict(arr_histogram(result)),
    }
    return payload


def _errors_response(errors: Errors) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"errors": [dataclasses.asdict(error) for error in errors]},
    )
