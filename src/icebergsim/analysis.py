"""Analysis of a 2x2 table (SPEC §7): effect measures, confidence intervals, p-values.

All functions are pure. Undefined quantities (division by zero without an explicit
zero-cell correction) are returned as None together with a diagnostic warning code,
never raised and never silently clipped (SPEC §3.3, AXIOMS §4).

New p-value methods are added by registering a pure function in ``P_VALUE_METHODS``;
existing functions are never modified for that.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import stats

from icebergsim.model import AnalysisResult, SimulationSummary, Table2x2

FloatArray = npt.NDArray[np.float64]

# A p-value function takes (control_events, control_observed, intervention_events,
# intervention_observed) and returns the two-sided p-value.
PValueFunction = Callable[[int, int, int, int], float]


def analyze_2x2(
    table: Table2x2,
    *,
    alpha: float = 0.05,
    p_value_method: str = "likelihood_ratio",
    zero_cell_correction: float | None = 0.5,
) -> AnalysisResult:
    """Analyze one observed 2x2 table per SPEC §7."""
    warnings: list[str] = []
    c, big_c = table.control_events, table.control_observed
    e, big_e = table.intervention_events, table.intervention_observed
    if big_c <= 0 or big_e <= 0:
        warnings.append("zero_denominator")
        return _null_result(tuple(warnings))

    cer, eer = c / big_c, e / big_e
    arr = cer - eer
    nnt, nnh = _nnt_nnh(arr, warnings)
    arr_ci = _wald_arr_ci(cer, eer, big_c, big_e, alpha)
    rr, rrr, rr_ci, rrr_ci = _relative_risk(
        c, big_c, e, big_e, alpha, zero_cell_correction, warnings
    )
    p_value = _p_value(p_value_method, c, big_c, e, big_e, warnings)
    return AnalysisResult(
        cer=cer,
        eer=eer,
        arr=arr,
        rr=rr,
        rrr=rrr,
        nnt=nnt,
        nnh=nnh,
        arr_ci=arr_ci,
        rr_ci=rr_ci,
        rrr_ci=rrr_ci,
        p_value=p_value,
        warnings=tuple(warnings),
    )


def _nnt_nnh(arr: float, warnings: list[str]) -> tuple[float | None, float | None]:
    """SPEC §7.2: NNT for benefit, NNH for harm, both None when ARR == 0."""
    if arr > 0.0:
        return 1.0 / arr, None
    if arr < 0.0:
        return None, -1.0 / arr
    warnings.append("no_absolute_difference")
    return None, None


def _wald_arr_ci(
    cer: float, eer: float, big_c: int, big_e: int, alpha: float
) -> tuple[float, float]:
    """SPEC §7.3: Wald confidence interval for the absolute risk difference."""
    se = math.sqrt(cer * (1.0 - cer) / big_c + eer * (1.0 - eer) / big_e)
    z = _z_two_sided(alpha)
    arr = cer - eer
    return arr - z * se, arr + z * se


def _relative_risk(
    c: float,
    big_c: float,
    e: float,
    big_e: float,
    alpha: float,
    zero_cell_correction: float | None,
    warnings: list[str],
) -> tuple[float | None, float | None, tuple[float, float] | None, tuple[float, float] | None]:
    """SPEC §7.1/§7.4: RR, RRR and their CIs; zero event cells use the correction or None."""
    if c == 0 or e == 0:
        warnings.append("zero_event_cell")
        if zero_cell_correction is None:
            return None, None, None, None
        warnings.append("zero_cell_correction_applied")
        k = zero_cell_correction
        c, e = c + k, e + k
        big_c, big_e = big_c + 2.0 * k, big_e + 2.0 * k
    rr = (e / big_e) / (c / big_c)
    rrr = 1.0 - rr
    se_log_rr = math.sqrt(1.0 / e - 1.0 / big_e + 1.0 / c - 1.0 / big_c)
    z = _z_two_sided(alpha)
    rr_lo = math.exp(math.log(rr) - z * se_log_rr)
    rr_hi = math.exp(math.log(rr) + z * se_log_rr)
    return rr, rrr, (rr_lo, rr_hi), (1.0 - rr_hi, 1.0 - rr_lo)


def _p_value(
    method: str, c: int, big_c: int, e: int, big_e: int, warnings: list[str]
) -> float | None:
    p_value_function = P_VALUE_METHODS.get(method)
    if p_value_function is None:
        warnings.append(f"p_value_method_unsupported:{method}")
        return None
    return p_value_function(c, big_c, e, big_e)


def _common_rate_expected(
    c: int, big_c: int, e: int, big_e: int
) -> tuple[tuple[int, ...], tuple[float, ...]] | None:
    """Observed and expected cell counts under a common event rate, or None if degenerate."""
    total_events = c + e
    if total_events == 0 or total_events == big_c + big_e:
        return None  # no outcome variation: both test statistics are exactly 0
    p_common = total_events / (big_c + big_e)
    observed = (c, big_c - c, e, big_e - e)
    expected = (
        big_c * p_common,
        big_c * (1.0 - p_common),
        big_e * p_common,
        big_e * (1.0 - p_common),
    )
    return observed, expected


def _likelihood_ratio_p(c: int, big_c: int, e: int, big_e: int) -> float:
    """SPEC §7.5: G-test; terms with O_j = 0 contribute zero."""
    cells = _common_rate_expected(c, big_c, e, big_e)
    if cells is None:
        return 1.0
    observed, expected = cells
    g = 2.0 * sum(
        o * math.log(o / exp) for o, exp in zip(observed, expected, strict=True) if o > 0
    )
    return float(stats.chi2.sf(max(g, 0.0), df=1))


def _pearson_chi_square_p(c: int, big_c: int, e: int, big_e: int) -> float:
    """SPEC §7.6: Pearson chi-square without continuity correction."""
    cells = _common_rate_expected(c, big_c, e, big_e)
    if cells is None:
        return 1.0
    observed, expected = cells
    x2 = sum((o - exp) ** 2 / exp for o, exp in zip(observed, expected, strict=True))
    return float(stats.chi2.sf(x2, df=1))


def _fisher_exact_p(c: int, big_c: int, e: int, big_e: int) -> float:
    """SPEC §7.7: Fisher's exact test, two-sided."""
    result = stats.fisher_exact(
        np.array([[e, big_e - e], [c, big_c - c]]), alternative="two-sided"
    )
    return float(result.pvalue)


P_VALUE_METHODS: dict[str, PValueFunction] = {
    "likelihood_ratio": _likelihood_ratio_p,
    "pearson_chi_square": _pearson_chi_square_p,
    "fisher_exact": _fisher_exact_p,
}


# --- batch analysis over simulation replicates (SPEC §6.3, §4.3, §9) ------------------------


@dataclass(frozen=True, slots=True)
class AnalysisBatch:
    """Per-replicate analysis arrays. RR/RRR hold NaN where undefined (null on export)."""

    cer: FloatArray
    eer: FloatArray
    arr: FloatArray
    rr: FloatArray
    rrr: FloatArray
    p_values: FloatArray
    zero_event_cell_count: int


def analyze_2x2_batch(
    control_events: npt.ArrayLike,
    control_observed: npt.ArrayLike,
    intervention_events: npt.ArrayLike,
    intervention_observed: npt.ArrayLike,
    *,
    p_value_method: str = "likelihood_ratio",
    zero_cell_correction: float | None = 0.5,
) -> AnalysisBatch:
    """Vectorized analysis of many 2x2 tables, exactly equivalent to analyze_2x2 per table."""
    c = np.asarray(control_events, dtype=np.float64)
    big_c = np.asarray(control_observed, dtype=np.float64)
    e = np.asarray(intervention_events, dtype=np.float64)
    big_e = np.asarray(intervention_observed, dtype=np.float64)

    cer, eer = c / big_c, e / big_e
    arr = cer - eer
    zero_mask = (c == 0) | (e == 0)
    if zero_cell_correction is None:
        safe_c = np.where(zero_mask, 1.0, c)  # dummy avoids 0/0; result masked to NaN below
        rr = np.where(zero_mask, np.nan, (e / big_e) / (safe_c / big_c))
    else:
        k = zero_cell_correction
        corr_c = np.where(zero_mask, c + k, c)
        corr_e = np.where(zero_mask, e + k, e)
        corr_big_c = np.where(zero_mask, big_c + 2.0 * k, big_c)
        corr_big_e = np.where(zero_mask, big_e + 2.0 * k, big_e)
        rr = (corr_e / corr_big_e) / (corr_c / corr_big_c)
    return AnalysisBatch(
        cer=cer,
        eer=eer,
        arr=arr,
        rr=rr,
        rrr=1.0 - rr,
        p_values=_batch_p_values(c, big_c, e, big_e, p_value_method),
        zero_event_cell_count=int(zero_mask.sum()),
    )


def _batch_p_values(
    c: FloatArray, big_c: FloatArray, e: FloatArray, big_e: FloatArray, method: str
) -> FloatArray:
    if method == "likelihood_ratio":
        return _chi2_sf(_batch_g_statistic(c, big_c, e, big_e))
    if method == "pearson_chi_square":
        return _chi2_sf(_batch_x2_statistic(c, big_c, e, big_e))
    p_value_function = P_VALUE_METHODS.get(method)
    if p_value_function is None:
        raise ValueError(f"unsupported p_value_method for batch analysis: {method!r}")
    # No vectorized form (e.g. Fisher exact): fall back to the scalar function per table.
    return np.array(
        [
            p_value_function(int(ci), int(big_ci), int(ei), int(big_ei))
            for ci, big_ci, ei, big_ei in zip(c, big_c, e, big_e, strict=True)
        ],
        dtype=np.float64,
    )


def _batch_observed_expected(
    c: FloatArray, big_c: FloatArray, e: FloatArray, big_e: FloatArray
) -> tuple[FloatArray, FloatArray]:
    p_common = (c + e) / (big_c + big_e)
    observed = np.stack([c, big_c - c, e, big_e - e])
    expected = np.stack(
        [big_c * p_common, big_c * (1.0 - p_common), big_e * p_common, big_e * (1.0 - p_common)]
    )
    return observed, expected


def _batch_g_statistic(
    c: FloatArray, big_c: FloatArray, e: FloatArray, big_e: FloatArray
) -> FloatArray:
    """SPEC §7.5 vectorized; O_j = 0 terms contribute zero, degenerate tables give G = 0."""
    observed, expected = _batch_observed_expected(c, big_c, e, big_e)
    ratio = np.where(observed > 0, observed / np.where(expected > 0, expected, 1.0), 1.0)
    g = 2.0 * np.sum(observed * np.log(ratio), axis=0)
    return np.maximum(g, 0.0)


def _batch_x2_statistic(
    c: FloatArray, big_c: FloatArray, e: FloatArray, big_e: FloatArray
) -> FloatArray:
    """SPEC §7.6 vectorized; zero expected cells only occur with zero observed cells."""
    observed, expected = _batch_observed_expected(c, big_c, e, big_e)
    contributions = (observed - expected) ** 2 / np.where(expected > 0, expected, 1.0)
    return np.asarray(np.sum(contributions, axis=0))


def _chi2_sf(statistic: FloatArray) -> FloatArray:
    return np.asarray(stats.chi2.sf(statistic, df=1), dtype=np.float64)


def summarize_batch(batch: AnalysisBatch, alpha: float) -> SimulationSummary:
    """Summarize per-replicate arrays into SPEC §4.3 summary statistics."""
    arr, rr = batch.arr, batch.rr
    n = arr.size
    power = float(np.mean(batch.p_values < alpha))
    defined_rr = rr[~np.isnan(rr)]
    benefit = arr[arr > 0.0]
    harm = arr[arr < 0.0]
    return SimulationSummary(
        mean_cer=float(batch.cer.mean()),
        mean_eer=float(batch.eer.mean()),
        mean_arr=float(arr.mean()),
        mean_rr=float(defined_rr.mean()) if defined_rr.size else None,
        mean_rrr=float(1.0 - defined_rr.mean()) if defined_rr.size else None,
        median_arr=float(np.median(arr)),
        ci95_arr_empirical=(
            float(np.percentile(arr, 2.5)),
            float(np.percentile(arr, 97.5)),
        ),
        ci95_rr_empirical=(
            (float(np.percentile(defined_rr, 2.5)), float(np.percentile(defined_rr, 97.5)))
            if defined_rr.size
            else (None, None)
        ),
        power=power,
        power_mcse=math.sqrt(power * (1.0 - power) / n),
        mean_nnt=float((1.0 / benefit).mean()) if benefit.size else None,
        mean_nnh=float((-1.0 / harm).mean()) if harm.size else None,
    )


def _z_two_sided(alpha: float) -> float:
    return float(stats.norm.ppf(1.0 - alpha / 2.0))


def _null_result(warnings: tuple[str, ...]) -> AnalysisResult:
    return AnalysisResult(
        cer=None,
        eer=None,
        arr=None,
        rr=None,
        rrr=None,
        nnt=None,
        nnh=None,
        arr_ci=None,
        rr_ci=None,
        rrr_ci=None,
        p_value=None,
        warnings=warnings,
    )
