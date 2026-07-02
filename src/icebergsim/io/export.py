"""Result export (SPEC §2.9, ARCHITECTURE §3.11).

Every export carries the reproducibility manifest (input hash, seed, RNG algorithm,
spec version, analysis method — AXIOMS §3). Undefined values (NaN-coded internally)
are exported as null, never as NaN: JSON is written with allow_nan=False so a leak
would fail loudly rather than produce unparseable output.

Supported formats: json, yaml, csv. Parquet is not supported by this implementation.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy.typing as npt
import yaml

from icebergsim.model import SimulationSummary
from icebergsim.simulate import SimulationResult

EXPORT_FORMATS = ("json", "yaml", "csv")


def summary_to_dict(summary: SimulationSummary) -> dict[str, Any]:
    """JSON-safe form of a SimulationSummary (undefined values as null)."""
    return {
        "mean_cer": _number(summary.mean_cer),
        "mean_eer": _number(summary.mean_eer),
        "mean_arr": _number(summary.mean_arr),
        "mean_rr": _number(summary.mean_rr),
        "mean_rrr": _number(summary.mean_rrr),
        "median_arr": _number(summary.median_arr),
        "ci95_arr_empirical": [_number(v) for v in summary.ci95_arr_empirical],
        "ci95_rr_empirical": [_number(v) for v in summary.ci95_rr_empirical],
        "power": _number(summary.power),
        "power_mcse": _number(summary.power_mcse),
        "type_i_error": _number(summary.type_i_error),
        "type_i_error_mcse": _number(summary.type_i_error_mcse),
        "mean_nnt": _number(summary.mean_nnt),
        "mean_nnh": _number(summary.mean_nnh),
    }


def to_json_safe(value: Any) -> Any:
    """Recursively convert NaN floats to None and tuples to lists for strict JSON."""
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_json_safe(item) for item in value]
    return value


def result_to_dict(result: SimulationResult, *, include_arrays: bool = True) -> dict[str, Any]:
    """Serialize a SimulationResult to plain JSON/YAML-safe data (SPEC §4.3 shape)."""
    payload: dict[str, Any] = {
        "manifest": {
            "input_hash": result.input_hash,
            "random_seed": result.random_seed,
            "n_simulations": result.n_simulations,
            "rng_algorithm": result.rng_algorithm,
            "spec_version": result.spec_version,
            "p_value_method": result.p_value_method,
            "alpha": result.alpha,
        },
        "summary": summary_to_dict(result.summary),
        "warnings": list(result.warnings),
        "notes": list(result.notes),
    }
    if include_arrays:
        payload["simulated_tables"] = {
            "control_events": result.tables.control_events.tolist(),
            "control_observed": result.tables.control_observed.tolist(),
            "intervention_events": result.tables.intervention_events.tolist(),
            "intervention_observed": result.tables.intervention_observed.tolist(),
        }
        payload["analysis_arrays"] = {
            "p_values": _nullable_array(result.arrays.p_values),
            "arr": _nullable_array(result.arrays.arr),
            "rr": _nullable_array(result.arrays.rr),
            "rrr": _nullable_array(result.arrays.rrr),
        }
    return payload


def summary_row(result: SimulationResult) -> dict[str, Any]:
    """One flat manifest + summary row, suitable for aligned CSV tables."""
    payload = result_to_dict(result, include_arrays=False)
    row: dict[str, Any] = dict(payload["manifest"])
    for key, value in payload["summary"].items():
        if isinstance(value, list):
            row[f"{key.removesuffix('_empirical')}_low"] = value[0]
            row[f"{key.removesuffix('_empirical')}_high"] = value[1]
        else:
            row[key] = value
    return row


def export_result(result: SimulationResult, path: Path | str, format: str) -> Path:
    """Write a result to disk in the requested format and return the path."""
    path = Path(path)
    if format == "json":
        path.write_text(
            json.dumps(result_to_dict(result), indent=2, allow_nan=False) + "\n"
        )
    elif format == "yaml":
        path.write_text(yaml.safe_dump(result_to_dict(result), sort_keys=False))
    elif format == "csv":
        write_rows_csv([summary_row(result)], path)
    else:
        raise ValueError(
            f"unsupported export format {format!r}; supported: {EXPORT_FORMATS} "
            "(parquet is not supported by this implementation)"
        )
    return path


def write_rows_csv(rows: Sequence[Mapping[str, Any]], path: Path | str) -> Path:
    """Write aligned-column rows (e.g. a scenario summary table) as CSV."""
    path = Path(path)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return path


def _number(value: float | None) -> float | None:
    """NaN-coded undefined values become null on export."""
    if value is None or math.isnan(value):
        return None
    return float(value)


def _nullable_array(array: npt.NDArray[Any]) -> list[float | None]:
    return [None if math.isnan(x) else float(x) for x in array.tolist()]
