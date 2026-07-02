"""Plot-data layer (SPEC §16, ARCHITECTURE §3.10).

Pure functions turning simulation results into plot-ready series. No rendering, no I/O:
front ends (web UI, notebooks, static exporters) consume these and only draw. Every series
is derived from the exported result arrays — never from separate hidden calculations
(SPEC §16). Undefined replicates (NaN-coded) become None, matching the export layer.

New plot types are added by registering a pure function in ``PLOT_TYPES``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from icebergsim.model import SimulationSummary
from icebergsim.simulate import PowerCurveResult, SimulationResult
from icebergsim.stopping import StoppingSimulationResult
from icebergsim.subgroups import RiskSubgroupResult


@dataclass(frozen=True, slots=True)
class ScatterPlotData:
    """One point per simulated trial (SPEC §16 plot 1)."""

    x: tuple[float | None, ...]
    y: tuple[float | None, ...]
    x_label: str
    y_label: str
    alpha: float  # significance threshold, for a reference line


@dataclass(frozen=True, slots=True)
class HistogramData:
    """Binned distribution of a per-replicate quantity (SPEC §16 plot 2)."""

    bin_edges: tuple[float, ...]
    counts: tuple[int, ...]
    n_defined: int
    n_undefined: int
    label: str


@dataclass(frozen=True, slots=True)
class PowerCurveData:
    """Power over total sample size with Monte Carlo error (SPEC §16 plot 3)."""

    total_n: tuple[int, ...]
    power: tuple[float, ...]
    power_mcse: tuple[float, ...]


def rr_vs_p_scatter(
    result: SimulationResult, *, measure: Literal["rr", "rrr"] = "rr"
) -> ScatterPlotData:
    """RR (or RRR) against the p-value; each point is one simulated trial."""
    values = result.arrays.rr if measure == "rr" else result.arrays.rrr
    return ScatterPlotData(
        x=_nullable(values),
        y=_nullable(result.arrays.p_values),
        x_label=measure,
        y_label="p_value",
        alpha=result.alpha,
    )


def arr_histogram(result: SimulationResult, *, bins: int = 40) -> HistogramData:
    """Distribution of the absolute risk reduction across replicates."""
    arr = result.arrays.arr
    defined = arr[~np.isnan(arr)]
    counts, edges = np.histogram(defined, bins=bins)
    return HistogramData(
        bin_edges=tuple(float(e) for e in edges),
        counts=tuple(int(c) for c in counts),
        n_defined=int(defined.size),
        n_undefined=int(arr.size - defined.size),
        label="arr",
    )


def power_curve_data(curve: PowerCurveResult) -> PowerCurveData:
    """Series form of a power curve result."""
    return PowerCurveData(
        total_n=tuple(p.total_n for p in curve.points),
        power=tuple(p.power for p in curve.points),
        power_mcse=tuple(p.power_mcse for p in curve.points),
    )


@dataclass(frozen=True, slots=True)
class StopByLookData:
    """Distribution of interim stops over looks (SPEC §16 plot 6)."""

    looks: tuple[int, ...]
    information_fractions: tuple[float, ...]
    proportions: tuple[float, ...]
    proportion_reaching_final: float


def stopping_look_distribution(result: StoppingSimulationResult) -> StopByLookData:
    """Per-look stop proportions plus the share of replicates reaching the final analysis."""
    plan = result.plan
    return StopByLookData(
        looks=tuple(range(1, plan.n_interims + 1)),
        information_fractions=plan.information_fractions,
        proportions=result.summary.proportion_stopped_by_look,
        proportion_reaching_final=1.0 - result.summary.proportion_stopped_any,
    )


@dataclass(frozen=True, slots=True)
class ForestRow:
    """One subgroup (or the count-aggregate) in the forest display (SPEC §16 plot 7)."""

    label: str
    rr: float | None
    rr_low: float | None
    rr_high: float | None
    arr: float | None
    arr_low: float | None
    arr_high: float | None
    is_aggregate: bool


@dataclass(frozen=True, slots=True)
class ForestData:
    rows: tuple[ForestRow, ...]


def subgroup_forest(result: RiskSubgroupResult) -> ForestData:
    """Forest-style rows: each subgroup's summary, then the count-aggregate (SPEC §12.2)."""
    rows = [
        _forest_row(subgroup.label, subgroup.result.summary, is_aggregate=False)
        for subgroup in result.subgroups
    ]
    rows.append(
        _forest_row("Aggregate (summed counts)", result.aggregate_summary, is_aggregate=True)
    )
    return ForestData(rows=tuple(rows))


def _forest_row(label: str, summary: SimulationSummary, *, is_aggregate: bool) -> ForestRow:
    return ForestRow(
        label=label,
        rr=summary.mean_rr,
        rr_low=summary.ci95_rr_empirical[0],
        rr_high=summary.ci95_rr_empirical[1],
        arr=summary.mean_arr,
        arr_low=summary.ci95_arr_empirical[0],
        arr_high=summary.ci95_arr_empirical[1],
        is_aggregate=is_aggregate,
    )



PLOT_TYPES: dict[str, Callable[[SimulationResult], ScatterPlotData | HistogramData]] = {
    "rr_vs_p": lambda result: rr_vs_p_scatter(result, measure="rr"),
    "rrr_vs_p": lambda result: rr_vs_p_scatter(result, measure="rrr"),
    "arr_histogram": arr_histogram,
}


def make_plot_data(
    result: SimulationResult, plot_type: str
) -> ScatterPlotData | HistogramData:
    """Dispatch to a registered plot-data function (ARCHITECTURE §3.10)."""
    plot_function = PLOT_TYPES.get(plot_type)
    if plot_function is None:
        raise ValueError(
            f"unknown plot_type {plot_type!r}; registered: {sorted(PLOT_TYPES)}"
        )
    return plot_function(result)


def _nullable(array: npt.NDArray[np.float64]) -> tuple[float | None, ...]:
    return tuple(None if np.isnan(value) else float(value) for value in array)
