"""Plot-data layer (SPEC §16, ARCHITECTURE §3.10).

Plot data is derived purely from result arrays — never from separate hidden calculations.
These tests check that every series aligns exactly with the exported arrays.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from icebergsim.plots import (
    PLOT_TYPES,
    arr_histogram,
    make_plot_data,
    power_curve_data,
    rr_vs_p_scatter,
    stopping_look_distribution,
    subgroup_forest,
)
from icebergsim.simulate import (
    PowerCurveResult,
    SimulationResult,
    simulate_power_curve,
    simulate_trial,
)
from icebergsim.stopping import simulate_with_stopping
from icebergsim.subgroups import simulate_risk_subgroups
from test_stopping import stopping_trial
from test_subgroups import validated_family
from trial_builders import make_validated


def result_of(n_simulations: int = 500, **overrides: object) -> SimulationResult:
    return simulate_trial(make_validated(n_simulations=n_simulations, **overrides))


def lossy_result() -> SimulationResult:
    """Small arms + heavy loss: produces genuinely undefined (NaN) replicates."""
    return simulate_trial(
        make_validated(
            n_simulations=500,
            allocation={"total_n": 8, "intervention_fraction": 0.5},
            imperfections={
                "control": {"loss_probability": 0.9},
                "intervention": {"loss_probability": 0.9},
            },
        )
    )


# --- RR/RRR vs p-value scatter (SPEC §16 plot 1) ---------------------------------------------


def test_scatter_aligns_with_result_arrays() -> None:
    result = result_of()
    data = rr_vs_p_scatter(result)
    assert len(data.x) == 500
    assert len(data.y) == 500
    for i in (0, 123, 499):
        rr = result.arrays.rr[i]
        assert data.x[i] == (None if math.isnan(rr) else float(rr))
        assert data.y[i] == float(result.arrays.p_values[i])
    assert data.x_label == "rr"
    assert data.y_label == "p_value"
    assert data.alpha == 0.05


def test_scatter_rrr_measure_uses_rrr_values() -> None:
    result = result_of(n_simulations=200)
    data = rr_vs_p_scatter(result, measure="rrr")
    assert data.x_label == "rrr"
    rrr = result.arrays.rrr
    assert data.x[0] == float(rrr[0])


def test_scatter_encodes_undefined_as_none() -> None:
    data = rr_vs_p_scatter(lossy_result())
    assert any(x is None for x in data.x)
    assert any(y is None for y in data.y)


# --- ARR histogram (SPEC §16 plot 2) ----------------------------------------------------------


def test_histogram_counts_cover_all_defined_replicates() -> None:
    result = result_of()
    data = arr_histogram(result, bins=25)
    assert len(data.bin_edges) == 26
    assert len(data.counts) == 25
    assert sum(data.counts) == data.n_defined == 500
    assert data.n_undefined == 0
    arr = result.arrays.arr
    assert data.bin_edges[0] <= float(np.min(arr))
    assert data.bin_edges[-1] >= float(np.max(arr))


def test_histogram_excludes_and_counts_undefined_replicates() -> None:
    data = arr_histogram(lossy_result())
    assert data.n_undefined > 0
    assert data.n_defined + data.n_undefined == 500
    assert sum(data.counts) == data.n_defined


# --- power curve (SPEC §16 plot 3) ------------------------------------------------------------


def test_power_curve_data_mirrors_curve_points() -> None:
    curve = simulate_power_curve(make_validated(n_simulations=500), (100, 400))
    assert isinstance(curve, PowerCurveResult)
    data = power_curve_data(curve)
    assert data.total_n == (100, 400)
    assert data.power == tuple(p.power for p in curve.points)
    assert data.power_mcse == tuple(p.power_mcse for p in curve.points)


# --- stopping-look distribution (SPEC §16 plot 6) ----------------------------------------------


def test_stopping_look_distribution_mirrors_result() -> None:
    result = simulate_with_stopping(stopping_trial(n_simulations=1000))
    data = stopping_look_distribution(result)
    assert data.looks == (1, 2, 3)
    assert data.information_fractions == (0.25, 0.5, 0.75)
    assert data.proportions == result.summary.proportion_stopped_by_look
    assert math.isclose(
        data.proportion_reaching_final,
        1.0 - result.summary.proportion_stopped_any,
        abs_tol=1e-12,
    )


# --- subgroup forest rows (SPEC §16 plot 7) -----------------------------------------------------


def test_subgroup_forest_rows_align_with_summaries() -> None:
    result = simulate_risk_subgroups(validated_family())
    forest = subgroup_forest(result)
    assert len(forest.rows) == 3
    assert [row.label for row in forest.rows[:2]] == ["High-risk patients", "Low-risk patients"]
    assert forest.rows[0].is_aggregate is False
    aggregate = forest.rows[-1]
    assert aggregate.is_aggregate is True
    assert aggregate.rr == result.aggregate_summary.mean_rr
    assert aggregate.rr_low == result.aggregate_summary.ci95_rr_empirical[0]
    assert aggregate.arr == result.aggregate_summary.mean_arr
    first = forest.rows[0]
    assert first.rr == result.subgroups[0].result.summary.mean_rr


# --- dispatcher (ARCHITECTURE §3.10 make_plot_data) --------------------------------------------


def test_make_plot_data_dispatches_registered_types() -> None:
    result = result_of(n_simulations=100)
    assert set(PLOT_TYPES) == {"rr_vs_p", "rrr_vs_p", "arr_histogram"}
    for plot_type in PLOT_TYPES:
        data = make_plot_data(result, plot_type)
        assert data is not None


def test_make_plot_data_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown plot_type"):
        make_plot_data(result_of(n_simulations=50), "pie_chart")
