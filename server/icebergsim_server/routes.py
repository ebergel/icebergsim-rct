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
from icebergsim.cluster import simulate_cluster_post_only, validate_cluster_trial
from icebergsim.cluster_pre_post import (
    simulate_cluster_pre_post,
    validate_cluster_pre_post_trial,
)
from icebergsim.io import load_definition, result_to_dict, summary_to_dict, to_json_safe
from icebergsim.model import ValidationError, validation_error
from icebergsim.plots import (
    arr_histogram,
    power_curve_data,
    rr_vs_p_scatter,
    stopping_look_distribution,
    subgroup_forest,
)
from icebergsim.rng import RNG_ALGORITHM
from icebergsim.sample_size import (
    calculate_cluster_post_sample_size,
    calculate_cluster_pre_post_sample_size,
    calculate_two_arm_sample_size,
)
from icebergsim.simulate import (
    PowerCurveResult,
    SimulationResult,
    simulate_power_curve,
    simulate_trial,
)
from icebergsim.stopping import STOPPING_RULES, simulate_with_stopping
from icebergsim.subgroups import (
    ValidatedSubgroupFamily,
    simulate_risk_subgroups,
    validate_subgroup_family,
)
from icebergsim.validate import (
    SUPPORTED_ANALYSIS_POPULATIONS,
    SUPPORTED_P_VALUE_METHODS,
    validate_trial_definition,
)

Errors = tuple[ValidationError, ...]


def api_router(examples_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api")
    _add_discovery_routes(router, examples_dir)
    _add_trial_routes(router)
    _add_planning_routes(router)
    _add_advanced_routes(router)
    return router


def _add_discovery_routes(router: APIRouter, examples_dir: Path) -> None:
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


def _add_trial_routes(router: APIRouter) -> None:
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


def _add_planning_routes(router: APIRouter) -> None:
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

    @router.post("/sample-size/cluster")
    def sample_size_cluster(params: dict[str, Any]) -> Any:
        numbers, errors = _read_numbers(
            params,
            required=("p_control", "p_intervention", "mean_cluster_size", "icc"),
            optional={"alpha": 0.05, "power": 0.80},
        )
        if errors:
            return _errors_response(tuple(errors))
        result = calculate_cluster_post_sample_size(
            p_control=numbers["p_control"],
            p_intervention=numbers["p_intervention"],
            alpha=numbers["alpha"],
            power=numbers["power"],
            alternative=str(params.get("alternative", "two_sided")),
            mean_cluster_size=numbers["mean_cluster_size"],
            icc=numbers["icc"],
        )
        if isinstance(result, tuple):
            return _errors_response(result)
        return dataclasses.asdict(result)

    @router.post("/sample-size/cluster-pre-post")
    def sample_size_cluster_pre_post(params: dict[str, Any]) -> Any:
        numbers, errors = _read_numbers(
            params,
            required=("p_control", "p_intervention", "mean_cluster_size", "icc",
                      "pre_post_correlation"),
            optional={"alpha": 0.05, "power": 0.80},
        )
        if errors:
            return _errors_response(tuple(errors))
        result = calculate_cluster_pre_post_sample_size(
            p_control=numbers["p_control"],
            p_intervention=numbers["p_intervention"],
            alpha=numbers["alpha"],
            power=numbers["power"],
            alternative=str(params.get("alternative", "two_sided")),
            mean_cluster_size=numbers["mean_cluster_size"],
            icc=numbers["icc"],
            pre_post_correlation=numbers["pre_post_correlation"],
        )
        if isinstance(result, tuple):
            return _errors_response(result)
        return dataclasses.asdict(result)

    @router.post("/cluster-pre-post")
    def cluster_pre_post(definition: dict[str, Any]) -> Any:
        validated = validate_cluster_pre_post_trial(definition)
        if isinstance(validated, tuple):
            return _errors_response(validated)
        result = simulate_cluster_pre_post(validated)
        return to_json_safe(
            {
                "manifest": {
                    "input_hash": result.input_hash,
                    "random_seed": result.random_seed,
                    "n_simulations": result.n_simulations,
                    "rng_algorithm": result.rng_algorithm,
                    "spec_version": result.spec_version,
                },
                "design": {
                    "control_clusters": validated.control_clusters,
                    "intervention_clusters": validated.intervention_clusters,
                    "mean_cluster_size": validated.mean_cluster_size,
                    "icc": validated.icc,
                    "pre_post_correlation": validated.pre_post_correlation,
                    "baseline_event_probability": validated.baseline_event_probability,
                },
                "summary": dataclasses.asdict(result.summary),
                "warnings": list(result.warnings),
                "notes": list(result.notes),
            }
        )

    @router.post("/cluster")
    def cluster(definition: dict[str, Any]) -> Any:
        validated = validate_cluster_trial(definition)
        if isinstance(validated, tuple):
            return _errors_response(validated)
        result = simulate_cluster_post_only(validated)
        return to_json_safe(
            {
                "manifest": {
                    "input_hash": result.input_hash,
                    "random_seed": result.random_seed,
                    "n_simulations": result.n_simulations,
                    "rng_algorithm": result.rng_algorithm,
                    "spec_version": result.spec_version,
                },
                "design": {
                    "control_clusters": validated.control_clusters,
                    "intervention_clusters": validated.intervention_clusters,
                    "mean_cluster_size": validated.mean_cluster_size,
                    "icc": validated.icc,
                    "size_distribution": dataclasses.asdict(validated.size_distribution),
                },
                "summary": dataclasses.asdict(result.summary),
                "notes": list(result.notes),
            }
        )


def _add_advanced_routes(router: APIRouter) -> None:
    @router.post("/stopping")
    def stopping(
        definition: dict[str, Any],
        include_type_i_error: bool = Query(default=False),
    ) -> Any:
        validated = validate_trial_definition(definition)
        if isinstance(validated, tuple):
            return _errors_response(validated)
        if validated.definition.stopping is None:
            return _errors_response(
                (
                    validation_error(
                        "stopping_plan_missing",
                        "definition has no enabled stopping plan.",
                        "stopping",
                    ),
                )
            )
        result = simulate_with_stopping(validated, include_type_i_error=include_type_i_error)
        return to_json_safe(
            {
                "manifest": {
                    "input_hash": result.input_hash,
                    "random_seed": result.random_seed,
                    "n_simulations": result.n_simulations,
                    "rng_algorithm": result.rng_algorithm,
                    "spec_version": result.spec_version,
                },
                "plan": dataclasses.asdict(result.plan),
                "look_sample_sizes": list(result.look_sample_sizes),
                "summary": dataclasses.asdict(result.summary),
                "plots": {
                    "stop_by_look": dataclasses.asdict(stopping_look_distribution(result))
                },
            }
        )

    @router.post("/subgroups")
    def subgroups(family_raw: dict[str, Any]) -> Any:
        family = validate_subgroup_family(family_raw)
        if not isinstance(family, ValidatedSubgroupFamily):
            return _errors_response(family)
        result = simulate_risk_subgroups(family)
        return to_json_safe(
            {
                "manifest": {
                    "input_hash": result.input_hash,
                    "random_seed": result.random_seed,
                    "n_simulations": result.n_simulations,
                    "rng_algorithm": result.rng_algorithm,
                    "spec_version": result.spec_version,
                },
                "subgroups": [
                    {
                        "id": subgroup_result.id,
                        "label": subgroup_result.label,
                        "n_control": subgroup.validated.n_control,
                        "n_intervention": subgroup.validated.n_intervention,
                        "summary": summary_to_dict(subgroup_result.result.summary),
                    }
                    for subgroup, subgroup_result in zip(
                        family.subgroups, result.subgroups, strict=True
                    )
                ],
                "aggregate": {"summary": summary_to_dict(result.aggregate_summary)},
                "plots": {"forest": dataclasses.asdict(subgroup_forest(result))},
                "warnings": list(result.warnings),
                "notes": [
                    "aggregate result computed from summed 2x2 counts per replicate; "
                    "subgroup effect measures are never averaged (SPEC §12.2)"
                ],
            }
        )


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
