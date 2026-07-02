"""REST API contract tests (ARCHITECTURE §3.12/§4): thin routes over domain services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from icebergsim_server.main import create_app
from trial_builders import make_raw


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_meta_reports_capabilities(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["spec_version"] == "2.0.0-alpha.1"
    assert meta["rng_algorithm"] == "PCG64"
    assert "likelihood_ratio" in meta["p_value_methods"]
    assert "peto" in meta["stopping_rules"]
    assert "json" in meta["export_formats"]


def test_examples_listed_and_loadable(client: TestClient) -> None:
    examples = client.get("/api/examples").json()
    names = [e["name"] for e in examples]
    assert "simple_two_arm" in names
    assert len(examples) == 4
    detail = client.get("/api/examples/simple_two_arm").json()
    assert detail["schema_version"] == "icebergsim.trial.v2"
    assert detail["arms"]["control"]["event_probability"] == 0.20


def test_unknown_example_is_404(client: TestClient) -> None:
    assert client.get("/api/examples/nope").status_code == 404
    assert client.get("/api/examples/..%2F..%2Fpyproject").status_code == 404


def test_validate_accepts_valid_definition(client: TestClient) -> None:
    response = client.post("/api/validate", json=make_raw())
    assert response.status_code == 200
    body = response.json()
    assert body == {"valid": True, "n_control": 200, "n_intervention": 200}


def test_validate_returns_structured_errors(client: TestClient) -> None:
    raw = make_raw(
        arms={
            "control": {"event_probability": 1.2},
            "intervention": {"event_probability": -0.1},
        }
    )
    response = client.post("/api/validate", json=raw)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert len(errors) == 2
    assert errors[0]["type"] == "ValidationError"
    assert errors[0]["code"] == "probability_out_of_bounds"
    assert errors[0]["path"] == "arms.control.event_probability"


def test_simulate_contract(client: TestClient) -> None:
    response = client.post("/api/simulate", json=make_raw(n_simulations=300))
    assert response.status_code == 200
    body = response.json()
    manifest = body["manifest"]
    assert manifest["rng_algorithm"] == "PCG64"
    assert manifest["n_simulations"] == 300
    assert manifest["alpha"] == 0.05
    assert 0.0 <= body["summary"]["power"] <= 1.0
    # Plot data always included, raw arrays only on request.
    assert len(body["plots"]["rr_vs_p"]["x"]) == 300
    assert len(body["plots"]["arr_histogram"]["counts"]) > 0
    assert "analysis_arrays" not in body


def test_simulate_optionally_includes_arrays_and_type_i(client: TestClient) -> None:
    response = client.post(
        "/api/simulate",
        params={"include_arrays": "true", "include_type_i_error": "true"},
        json=make_raw(n_simulations=200),
    )
    body = response.json()
    assert len(body["analysis_arrays"]["p_values"]) == 200
    assert len(body["simulated_tables"]["control_events"]) == 200
    assert body["summary"]["type_i_error"] is not None


def test_simulate_rejects_invalid_definition(client: TestClient) -> None:
    response = client.post("/api/simulate", json=make_raw(alpha=7))
    assert response.status_code == 422
    assert any(e["code"] == "alpha_out_of_bounds" for e in response.json()["errors"])


def test_static_spa_served_when_built(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><body>icebergsim</body></html>")
    with TestClient(create_app(static_dir=tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "icebergsim" in response.text


def test_api_reachable_without_built_spa() -> None:
    with TestClient(create_app(static_dir=None)) as client:
        assert client.get("/api/meta").status_code == 200


def test_simulate_response_is_strict_json(client: TestClient) -> None:
    """NaN must never leak into the wire format (undefined -> null)."""
    lossy: dict[str, Any] = make_raw(
        n_simulations=300,
        allocation={"total_n": 8, "intervention_fraction": 0.5},
        imperfections={
            "control": {"loss_probability": 0.9},
            "intervention": {"loss_probability": 0.9},
        },
    )
    response = client.post("/api/simulate", params={"include_arrays": "true"}, json=lossy)
    assert response.status_code == 200
    assert "NaN" not in response.text
    body = response.json()
    assert any(value is None for value in body["analysis_arrays"]["arr"])
