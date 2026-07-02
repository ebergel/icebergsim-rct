"""Export layer and definition loading (SPEC §2.9, ARCHITECTURE §3.11)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml

from icebergsim.io import export_result, load_definition, result_to_dict
from icebergsim.model import ValidatedTrial
from icebergsim.simulate import simulate_trial
from icebergsim.validate import validate_trial_definition
from trial_builders import make_raw, make_validated


def test_result_to_dict_carries_manifest_summary_and_arrays() -> None:
    result = simulate_trial(make_validated(n_simulations=200))
    payload = result_to_dict(result)
    manifest = payload["manifest"]
    assert manifest["input_hash"] == result.input_hash
    assert manifest["random_seed"] == 12345
    assert manifest["rng_algorithm"] == "PCG64"
    assert manifest["spec_version"] == "2.0.0-alpha.1"
    assert manifest["p_value_method"] == "likelihood_ratio"
    assert payload["summary"]["power"] == result.summary.power
    assert len(payload["analysis_arrays"]["p_values"]) == 200
    assert len(payload["simulated_tables"]["control_events"]) == 200


def test_json_export_round_trips(tmp_path: Path) -> None:
    result = simulate_trial(make_validated(n_simulations=100))
    path = export_result(result, tmp_path / "result.json", "json")
    loaded = json.loads(path.read_text())
    assert loaded["manifest"]["input_hash"] == result.input_hash
    assert loaded["manifest"]["n_simulations"] == 100
    assert loaded["summary"]["power"] == result.summary.power


def test_yaml_export_parses(tmp_path: Path) -> None:
    result = simulate_trial(make_validated(n_simulations=100))
    path = export_result(result, tmp_path / "result.yaml", "yaml")
    loaded = yaml.safe_load(path.read_text())
    assert loaded["manifest"]["rng_algorithm"] == "PCG64"


def test_csv_export_is_one_aligned_row(tmp_path: Path) -> None:
    result = simulate_trial(make_validated(n_simulations=100))
    path = export_result(result, tmp_path / "result.csv", "csv")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["input_hash"] == result.input_hash
    assert float(rows[0]["power"]) == result.summary.power


def test_undefined_values_export_as_null_not_nan(tmp_path: Path) -> None:
    # High loss with tiny arms produces zero-denominator replicates (NaN internally).
    result = simulate_trial(
        make_validated(
            n_simulations=500,
            allocation={"total_n": 8, "intervention_fraction": 0.5},
            imperfections={
                "control": {"loss_probability": 0.9},
                "intervention": {"loss_probability": 0.9},
            },
        )
    )
    path = export_result(result, tmp_path / "result.json", "json")
    loaded = json.loads(path.read_text())  # would fail if NaN leaked (allow_nan=False)
    assert any(value is None for value in loaded["analysis_arrays"]["arr"])
    assert any(w.startswith("zero_denominator_replicates:") for w in loaded["warnings"])


def test_unsupported_format_rejected(tmp_path: Path) -> None:
    result = simulate_trial(make_validated(n_simulations=50))
    with pytest.raises(ValueError, match="parquet"):
        export_result(result, tmp_path / "result.parquet", "parquet")


def test_load_definition_yaml_and_json(tmp_path: Path) -> None:
    raw = make_raw()
    yaml_path = tmp_path / "trial.yaml"
    yaml_path.write_text(yaml.safe_dump(raw))
    json_path = tmp_path / "trial.json"
    json_path.write_text(json.dumps(raw))
    for path in (yaml_path, json_path):
        loaded = load_definition(path)
        assert isinstance(validate_trial_definition(loaded), ValidatedTrial), path
