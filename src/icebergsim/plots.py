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

from icebergsim.simulate import PowerCurveResult, SimulationResult


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
