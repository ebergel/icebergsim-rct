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
from icebergsim.model import ValidationError
from icebergsim.plots import arr_histogram, rr_vs_p_scatter
from icebergsim.rng import RNG_ALGORITHM
from icebergsim.simulate import SimulationResult, simulate_trial
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

    return router


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
