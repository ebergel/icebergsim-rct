"""Risk subgroup simulation (SPEC §12) and multi-scenario comparison (§13)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from icebergsim.model import Table2x2, ValidationError
from icebergsim.scenarios import (
    ScenarioFamilyResult,
    scenario_summary_table,
    simulate_scenario_family,
)
from icebergsim.subgroups import (
    RiskSubgroupResult,
    ValidatedSubgroupFamily,
    aggregate_subgroup_tables,
    simulate_risk_subgroups,
    validate_subgroup_family,
)
from trial_builders import make_raw

Errors = tuple[ValidationError, ...]


def family_raw(**overrides: Any) -> dict[str, Any]:
    high = make_raw(
        id="high_risk",
        label="High-risk patients",
        n_simulations=3000,
        random_seed=777,
        arms={
            "control": {"event_probability": 0.30},
            "intervention": {"event_probability": 0.15},
        },
        allocation={"total_n": 200, "intervention_fraction": 0.5},
    )
    low = make_raw(
        id="low_risk",
        label="Low-risk patients",
        n_simulations=3000,
        random_seed=777,
        arms={
            "control": {"event_probability": 0.10},
            "intervention": {"event_probability": 0.05},
        },
        allocation={"total_n": 200, "intervention_fraction": 0.5},
    )
    raw: dict[str, Any] = {
        "subgroups": [
            {"id": "high_risk", "label": "High-risk patients", "weight": None, "trial": high},
            {"id": "low_risk", "label": "Low-risk patients", "weight": None, "trial": low},
        ]
    }
    raw.update(overrides)
    return raw


def validated_family(**overrides: Any) -> ValidatedSubgroupFamily:
    result = validate_subgroup_family(family_raw(**overrides))
    assert isinstance(result, ValidatedSubgroupFamily), result
    return result


def family_codes(raw: dict[str, Any]) -> list[str]:
    result = validate_subgroup_family(raw)
    assert isinstance(result, tuple), f"expected errors, got {result}"
    return [e.code for e in result]


# --- count aggregation (SPEC §12.2) ----------------------------------------------------------


def test_aggregate_sums_counts_not_effects() -> None:
    """Canonical: RRs 1/3 and 1.0 would average to 2/3; summed counts give RR 0.5."""
    aggregate = aggregate_subgroup_tables(
        [
            Table2x2(30, 100, 10, 100),
            Table2x2(10, 100, 10, 100),
        ]
    )
    assert aggregate == Table2x2(40, 200, 20, 200)


# --- family validation -----------------------------------------------------------------------


def test_valid_family_preserves_ids_and_labels() -> None:
    family = validated_family()
    assert [s.id for s in family.subgroups] == ["high_risk", "low_risk"]
    assert family.subgroups[0].label == "High-risk patients"
    assert family.subgroups[0].validated.n_control == 100


def test_mismatched_n_simulations_rejected() -> None:
    raw = family_raw()
    raw["subgroups"][1]["trial"]["n_simulations"] = 500
    assert "subgroup_n_simulations_mismatch" in family_codes(raw)


def test_mismatched_seed_rejected() -> None:
    raw = family_raw()
    raw["subgroups"][1]["trial"]["random_seed"] = 42
    assert "subgroup_seed_mismatch" in family_codes(raw)


def test_mismatched_analysis_policy_rejected() -> None:
    raw = family_raw()
    raw["subgroups"][1]["trial"]["alpha"] = 0.01
    assert "subgroup_analysis_mismatch" in family_codes(raw)


def test_duplicate_subgroup_ids_rejected() -> None:
    raw = family_raw()
    raw["subgroups"][1]["id"] = "high_risk"
    assert "subgroup_duplicate_id" in family_codes(raw)


def test_empty_family_rejected() -> None:
    assert "subgroup_family_empty" in family_codes({"subgroups": []})


def test_invalid_subgroup_trial_error_carries_indexed_path() -> None:
    raw = family_raw()
    raw["subgroups"][1]["trial"]["arms"]["control"]["event_probability"] = 1.5
    result = validate_subgroup_family(raw)
    assert isinstance(result, tuple)
    assert any(e.path.startswith("subgroups[1].trial") for e in result)


# --- subgroup simulation (SPEC §12) ----------------------------------------------------------


def test_aggregate_tables_are_exact_per_replicate_sums() -> None:
    """ARCHITECTURE invariant 5 / property subgroup_aggregate_is_sum_of_counts."""
    result = simulate_risk_subgroups(validated_family())
    assert isinstance(result, RiskSubgroupResult)
    for field in (
        "control_events",
        "control_observed",
        "intervention_events",
        "intervention_observed",
    ):
        summed = np.sum(
            [getattr(s.result.tables, field) for s in result.subgroups], axis=0
        )
        assert np.array_equal(getattr(result.aggregate_tables, field), summed), field


def test_aggregate_rates_match_pooled_truth() -> None:
    result = simulate_risk_subgroups(validated_family())
    # Pooled truth: (0.30*100 + 0.10*100) / 200 = 0.20 control, 0.10 intervention.
    assert math.isclose(result.aggregate_summary.mean_cer, 0.20, abs_tol=0.01)
    assert math.isclose(result.aggregate_summary.mean_eer, 0.10, abs_tol=0.01)
    assert result.aggregate_summary.mean_rr is not None
    assert math.isclose(result.aggregate_summary.mean_rr, 0.5, abs_tol=0.05)


def test_subgroup_streams_are_independent() -> None:
    """Identical subgroup definitions must still receive independent randomness."""
    raw = family_raw()
    raw["subgroups"][1]["trial"] = dict(raw["subgroups"][0]["trial"], id="clone")
    raw["subgroups"][1]["id"] = "clone"
    result = simulate_risk_subgroups(validated_family(**raw))
    a, b = result.subgroups
    assert not np.array_equal(a.result.tables.control_events, b.result.tables.control_events)


def test_subgroup_simulation_reproducible() -> None:
    a = simulate_risk_subgroups(validated_family())
    b = simulate_risk_subgroups(validated_family())
    assert np.array_equal(a.aggregate_tables.control_events, b.aggregate_tables.control_events)
    assert np.array_equal(a.aggregate_arrays.p_values, b.aggregate_arrays.p_values)


def test_subgroup_result_carries_manifest() -> None:
    result = simulate_risk_subgroups(validated_family())
    assert result.rng_algorithm == "PCG64"
    assert result.spec_version == "2.0.0-alpha.1"
    assert result.n_simulations == 3000
    assert result.random_seed == 777
    assert len(result.input_hash) == 64


# --- multi-scenario comparison (SPEC §13) ----------------------------------------------------


def test_scenario_family_simulates_independently_and_aligns_columns() -> None:
    ideal = make_raw(id="ideal", label="Ideal trial", n_simulations=2000)
    worse = make_raw(
        id="pragmatic",
        label="Pragmatic trial",
        n_simulations=2000,
        imperfections={
            "control": {"loss_probability": 0.1},
            "intervention": {"loss_probability": 0.1, "noncompliance_probability": 0.2},
        },
    )
    family = simulate_scenario_family([ideal, worse])
    assert isinstance(family, ScenarioFamilyResult)
    assert [s.id for s in family.scenarios] == ["ideal", "pragmatic"]
    assert [s.label for s in family.scenarios] == ["Ideal trial", "Pragmatic trial"]
    assert family.scenarios[1].result.summary.power < family.scenarios[0].result.summary.power
    # SPEC §13: no statistical-difference claim.
    assert any("no statistical comparison" in note for note in family.notes)

    table = scenario_summary_table(family)
    assert len(table) == 2
    assert list(table[0].keys()) == list(table[1].keys())  # aligned columns
    assert table[0]["id"] == "ideal"
    assert table[1]["power"] == family.scenarios[1].result.summary.power


def test_scenario_family_validates_each_scenario_independently() -> None:
    good = make_raw(id="good")
    bad = make_raw(id="bad", alpha=7)
    also_bad = make_raw(id="also_bad", n_simulations=0)
    result = simulate_scenario_family([good, bad, also_bad])
    assert isinstance(result, tuple)
    paths = [e.path for e in result]
    assert any(p.startswith("scenarios[1].") for p in paths)
    assert any(p.startswith("scenarios[2].") for p in paths)
