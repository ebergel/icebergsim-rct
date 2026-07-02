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


def test_sample_size_two_arm_canonical(client: TestClient) -> None:
    response = client.post(
        "/api/sample-size/two-arm",
        json={"p_control": 0.20, "p_intervention": 0.10, "alpha": 0.05, "power": 0.80},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["n_control"] == 197
    assert body["n_intervention"] == 197
    assert body["n_total"] == 394
    assert abs(body["unrounded_n_control"] - 196.22199335872716) < 1e-9
    assert "formula" in body


def test_sample_size_two_arm_rejects_bad_inputs(client: TestClient) -> None:
    equal = client.post(
        "/api/sample-size/two-arm", json={"p_control": 0.2, "p_intervention": 0.2}
    )
    assert equal.status_code == 422
    assert any(e["code"] == "effect_size_zero" for e in equal.json()["errors"])
    wrong_type = client.post(
        "/api/sample-size/two-arm", json={"p_control": "high", "p_intervention": 0.1}
    )
    assert wrong_type.status_code == 422
    assert any(e["code"] == "invalid_type" for e in wrong_type.json()["errors"])
    missing = client.post("/api/sample-size/two-arm", json={"p_control": 0.2})
    assert missing.status_code == 422
    assert any(e["code"] == "missing_field" for e in missing.json()["errors"])


def test_power_curve_contract(client: TestClient) -> None:
    response = client.post(
        "/api/power-curve",
        json={
            "definition": make_raw(n_simulations=500),
            "total_sample_sizes": [100, 400],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [p["total_n"] for p in body["points"]] == [100, 400]
    assert all(0.0 <= p["power"] <= 1.0 for p in body["points"])
    assert body["plot"]["total_n"] == [100, 400]
    assert body["plot"]["power"] == [p["power"] for p in body["points"]]
    assert body["rng_algorithm"] == "PCG64"


def test_power_curve_rejects_bad_requests(client: TestClient) -> None:
    no_sizes = client.post("/api/power-curve", json={"definition": make_raw()})
    assert no_sizes.status_code == 422
    assert any(e["code"] == "missing_field" for e in no_sizes.json()["errors"])
    bad_sizes = client.post(
        "/api/power-curve",
        json={"definition": make_raw(), "total_sample_sizes": [0, 400]},
    )
    assert bad_sizes.status_code == 422
    assert any(e["code"] == "power_curve_sizes_invalid" for e in bad_sizes.json()["errors"])
    bad_definition = client.post(
        "/api/power-curve",
        json={"definition": make_raw(alpha=7), "total_sample_sizes": [100]},
    )
    assert bad_definition.status_code == 422
    assert any(e["code"] == "alpha_out_of_bounds" for e in bad_definition.json()["errors"])


def stopping_raw(**overrides: Any) -> dict[str, Any]:
    raw = make_raw(
        n_simulations=2000,
        allocation={"total_n": 800, "intervention_fraction": 0.5},
        stopping={"enabled": True, "rule": "peto", "n_interims": 3},
    )
    raw.update(overrides)
    return raw


def family_payload() -> dict[str, Any]:
    def trial(control: float, intervention: float) -> dict[str, Any]:
        return make_raw(
            n_simulations=1500,
            random_seed=777,
            arms={
                "control": {"event_probability": control},
                "intervention": {"event_probability": intervention},
            },
            allocation={"total_n": 200, "intervention_fraction": 0.5},
        )

    return {
        "subgroups": [
            {"id": "high", "label": "High risk", "weight": None, "trial": trial(0.30, 0.15)},
            {"id": "low", "label": "Low risk", "weight": None, "trial": trial(0.10, 0.05)},
        ]
    }


def test_stopping_contract(client: TestClient) -> None:
    response = client.post("/api/stopping", json=stopping_raw())
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["interim_p_thresholds"] == [0.001, 0.001, 0.001]
    assert body["plan"]["final_p_threshold"] == 0.05
    assert body["look_sample_sizes"][-1] == [400, 400]
    summary = body["summary"]
    assert 0.0 <= summary["proportion_stopped_any"] <= 1.0
    assert 0.0 <= summary["final_power_including_stops"] <= 1.0
    assert summary["type_i_error_including_stops"] is None
    plot = body["plots"]["stop_by_look"]
    assert plot["looks"] == [1, 2, 3]
    assert plot["information_fractions"] == [0.25, 0.5, 0.75]
    assert len(plot["proportions"]) == 3
    assert body["manifest"]["rng_algorithm"] == "PCG64"
    assert "NaN" not in response.text


def test_stopping_type_i_on_request(client: TestClient) -> None:
    response = client.post(
        "/api/stopping",
        params={"include_type_i_error": "true"},
        json=stopping_raw(n_simulations=1000),
    )
    assert response.json()["summary"]["type_i_error_including_stops"] is not None


def test_stopping_requires_a_plan(client: TestClient) -> None:
    response = client.post("/api/stopping", json=make_raw())
    assert response.status_code == 422
    assert any(e["code"] == "stopping_plan_missing" for e in response.json()["errors"])
    bad = client.post(
        "/api/stopping",
        json=stopping_raw(
            stopping={
                "rule": "custom",
                "n_interims": 3,
                "interim_p_thresholds": [0.001, 0.01],
                "final_p_threshold": 0.05,
            }
        ),
    )
    assert bad.status_code == 422
    assert any(
        e["code"] == "stopping_threshold_length_mismatch" for e in bad.json()["errors"]
    )


def test_subgroups_contract(client: TestClient) -> None:
    response = client.post("/api/subgroups", json=family_payload())
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["subgroups"]] == ["high", "low"]
    assert body["subgroups"][0]["label"] == "High risk"
    assert body["subgroups"][0]["n_control"] == 100
    assert 0.0 <= body["subgroups"][0]["summary"]["power"] <= 1.0
    assert 0.0 <= body["aggregate"]["summary"]["power"] <= 1.0
    rows = body["plots"]["forest"]["rows"]
    assert len(rows) == 3
    assert rows[-1]["is_aggregate"] is True
    assert rows[-1]["label"].startswith("Aggregate")
    assert any("summed 2x2 counts" in note for note in body["notes"])
    assert "NaN" not in response.text


def test_subgroups_family_errors(client: TestClient) -> None:
    payload = family_payload()
    payload["subgroups"][1]["trial"]["random_seed"] = 42
    response = client.post("/api/subgroups", json=payload)
    assert response.status_code == 422
    assert any(e["code"] == "subgroup_seed_mismatch" for e in response.json()["errors"])


def cluster_payload(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "icebergsim.trial.v2",
        "id": "cluster_ui",
        "label": "Cluster trial",
        "mode": "cluster_post",
        "n_simulations": 2000,
        "random_seed": 303,
        "alpha": 0.05,
        "arms": {
            "control": {"event_probability": 0.20},
            "intervention": {"event_probability": 0.10},
        },
        "clusters": {
            "control_clusters": 4,
            "intervention_clusters": 4,
            "mean_cluster_size": 100,
            "cluster_size_distribution": {"type": "fixed"},
        },
        "icc": 0.01,
    }
    raw.update(overrides)
    return raw


def test_cluster_sample_size_contract(client: TestClient) -> None:
    response = client.post(
        "/api/sample-size/cluster",
        json={
            "p_control": 0.20,
            "p_intervention": 0.10,
            "alpha": 0.05,
            "power": 0.80,
            "mean_cluster_size": 100,
            "icc": 0.01,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert abs(body["design_effect"] - 1.99) < 1e-12
    assert abs(body["cluster_adjusted_n_per_arm_unrounded"] - 390.48176678386704) < 1e-9
    assert body["clusters_per_arm"] == 4
    missing = client.post("/api/sample-size/cluster", json={"p_control": 0.2})
    assert missing.status_code == 422


def test_cluster_simulation_contract(client: TestClient) -> None:
    response = client.post("/api/cluster", json=cluster_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["design"]["control_clusters"] == 4
    assert body["design"]["icc"] == 0.01
    summary = body["summary"]
    assert abs(summary["mean_design_effect"] - 1.99) < 1e-9  # fixed sizes
    for key in (
        "power_unadjusted_chi_square",
        "power_adjusted_chi_square",
        "power_cluster_level_difference",
    ):
        assert 0.0 <= summary[key] <= 1.0
    assert summary["power_unadjusted_chi_square"] >= summary["power_adjusted_chi_square"]
    assert any("anti-conservative" in note for note in body["notes"])
    assert body["manifest"]["rng_algorithm"] == "PCG64"
    assert "NaN" not in response.text


def test_cluster_simulation_rejects_bad_definitions(client: TestClient) -> None:
    bad_icc = client.post("/api/cluster", json=cluster_payload(icc=1.0))
    assert bad_icc.status_code == 422
    assert any(e["code"] == "icc_out_of_bounds" for e in bad_icc.json()["errors"])
    wrong_mode = client.post("/api/cluster", json=cluster_payload(mode="individual_binary"))
    assert wrong_mode.status_code == 422
    assert any(e["code"] == "invalid_mode" for e in wrong_mode.json()["errors"])


def pre_post_payload(**overrides: Any) -> dict[str, Any]:
    raw = cluster_payload(
        id="pre_post_ui",
        mode="cluster_pre_post",
        baseline_event_probability=0.20,
        pre_post_correlation=0.5,
    )
    raw["clusters"]["control_clusters"] = 8
    raw["clusters"]["intervention_clusters"] = 8
    raw.update(overrides)
    return raw


def test_cluster_pre_post_sample_size_contract(client: TestClient) -> None:
    response = client.post(
        "/api/sample-size/cluster-pre-post",
        json={
            "p_control": 0.20,
            "p_intervention": 0.10,
            "alpha": 0.05,
            "power": 0.80,
            "mean_cluster_size": 100,
            "icc": 0.01,
            "pre_post_correlation": 0.5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["clusters_per_arm"] == 8
    assert body["n_per_arm"] > 0
    assert "formula" in body
    missing = client.post("/api/sample-size/cluster-pre-post", json={"p_control": 0.2})
    assert missing.status_code == 422


def test_cluster_pre_post_simulation_contract(client: TestClient) -> None:
    response = client.post("/api/cluster-pre-post", json=pre_post_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["design"]["pre_post_correlation"] == 0.5
    assert body["design"]["baseline_event_probability"] == 0.20
    summary = body["summary"]
    assert 0.0 <= summary["power_change_score"] <= 1.0
    assert 0.0 <= summary["power_followup_only"] <= 1.0
    assert abs(summary["mean_baseline_cer"] - 0.20) < 0.02
    assert abs(summary["mean_followup_eer"] - 0.10) < 0.02
    assert summary["mean_did"] > 0.05
    assert any("change-score" in note for note in body["notes"])
    assert body["manifest"]["rng_algorithm"] == "PCG64"
    assert "NaN" not in response.text


def test_cluster_pre_post_rejections(client: TestClient) -> None:
    bad_corr = client.post(
        "/api/cluster-pre-post", json=pre_post_payload(pre_post_correlation=1.5)
    )
    assert bad_corr.status_code == 422
    assert any(e["code"] == "correlation_out_of_bounds" for e in bad_corr.json()["errors"])
    truncating = client.post(
        "/api/cluster-pre-post",
        json=pre_post_payload(
            arms={
                "control": {"event_probability": 0.03},
                "intervention": {"event_probability": 0.03},
            },
            baseline_event_probability=0.03,
            icc=0.20,
        ),
    )
    assert truncating.status_code == 422
    assert any(
        e["code"] == "cluster_rate_truncation_excessive" for e in truncating.json()["errors"]
    )


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
