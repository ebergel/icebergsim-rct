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
    """SPEC §7.1/§7.4 zero-event-cell semantics:

    - c == 0 (CER = 0): RR is undefined (§3.3) — null unless a correction is selected,
      in which case RR and its CI both come from the corrected cells.
    - e == 0 with c > 0: RR is defined and exactly 0 (§7.1); the correction applies
      to the CI only (§7.4: "for the RR CI only").
    - Otherwise: uncorrected RR and log-RR CI.
    """
    if c > 0 and e > 0:
        rr = (e / big_e) / (c / big_c)
        rr_ci = _log_rr_ci(rr, c, big_c, e, big_e, alpha)
        return rr, 1.0 - rr, rr_ci, _reverse_ci(rr_ci)

    warnings.append("zero_event_cell")
    # A non-positive correction cannot remove the zero cell; treat it as disabled.
    if zero_cell_correction is None or zero_cell_correction <= 0.0:
        if c == 0:
            return None, None, None, None
        return 0.0, 1.0, None, None
    warnings.append("zero_cell_correction_applied")
    k = zero_cell_correction
    corrected_c, corrected_e = c + k, e + k
    corrected_big_c, corrected_big_e = big_c + 2.0 * k, big_e + 2.0 * k
    corrected_rr = (corrected_e / corrected_big_e) / (corrected_c / corrected_big_c)
    rr_ci = _log_rr_ci(
        corrected_rr, corrected_c, corrected_big_c, corrected_e, corrected_big_e, alpha
    )
    rr = corrected_rr if c == 0 else 0.0
    return rr, 1.0 - rr, rr_ci, _reverse_ci(rr_ci)


def _log_rr_ci(
    rr: float, c: float, big_c: float, e: float, big_e: float, alpha: float
) -> tuple[float, float]:
    """SPEC §7.4 log-RR Wald interval from the (possibly corrected) cells."""
    se_log_rr = math.sqrt(1.0 / e - 1.0 / big_e + 1.0 / c - 1.0 / big_c)
    z = _z_two_sided(alpha)
    return math.exp(math.log(rr) - z * se_log_rr), math.exp(math.log(rr) + z * se_log_rr)


def _reverse_ci(rr_ci: tuple[float, float]) -> tuple[float, float]:
    """RRR CI = 1 - reversed RR CI (SPEC §7.4)."""
    return 1.0 - rr_ci[1], 1.0 - rr_ci[0]


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
    """Per-replicate analysis arrays, read-only. NaN encodes undefined (null on export)."""

    cer: FloatArray
    eer: FloatArray
    arr: FloatArray
    rr: FloatArray
    rrr: FloatArray
    p_values: FloatArray
    zero_event_cell_count: int
    zero_denominator_count: int


def analyze_2x2_batch(
    control_events: npt.ArrayLike,
    control_observed: npt.ArrayLike,
    intervention_events: npt.ArrayLike,
    intervention_observed: npt.ArrayLike,
    *,
    p_value_method: str = "likelihood_ratio",
    zero_cell_correction: float | None = 0.5,
) -> AnalysisBatch:
    """Vectorized analysis of many 2x2 tables, exactly equivalent to analyze_2x2 per table.

    Replicates where either observed denominator is zero (possible when everyone in an arm
    is lost to follow-up) get NaN in every output, mirroring the scalar zero_denominator
    behavior (SPEC §3.3); they are counted in ``zero_denominator_count``.
    """
    c = np.asarray(control_events, dtype=np.float64)
    big_c = np.asarray(control_observed, dtype=np.float64)
    e = np.asarray(intervention_events, dtype=np.float64)
    big_e = np.asarray(intervention_observed, dtype=np.float64)

    invalid = (big_c <= 0) | (big_e <= 0)
    safe_big_c = np.where(big_c > 0, big_c, 1.0)
    safe_big_e = np.where(big_e > 0, big_e, 1.0)
    cer = np.where(invalid, np.nan, c / safe_big_c)
    eer = np.where(invalid, np.nan, e / safe_big_e)
    arr = cer - eer

    # SPEC §7.1/§7.4 zero-event-cell semantics, identical to the scalar path:
    # c == 0 -> RR undefined unless corrected; e == 0 with c > 0 -> RR is exactly 0.
    zero_event = ((c == 0) | (e == 0)) & ~invalid
    control_zero = (c == 0) & ~invalid
    safe_c = np.where(c > 0, c, 1.0)
    rr = (e / safe_big_e) / (safe_c / safe_big_c)  # rows with e == 0 are exactly 0 here
    if zero_cell_correction is None or zero_cell_correction <= 0.0:
        rr = np.where(control_zero, np.nan, rr)
    else:
        k = zero_cell_correction
        corrected_rr = ((e + k) / (big_e + 2.0 * k)) / ((c + k) / (big_c + 2.0 * k))
        rr = np.where(control_zero, corrected_rr, rr)
    rr = np.where(invalid, np.nan, rr)

    p_values = _batch_p_values(c, safe_big_c, e, safe_big_e, p_value_method)
    p_values = np.where(invalid, np.nan, p_values)
    return AnalysisBatch(
        cer=_read_only(cer),
        eer=_read_only(eer),
        arr=_read_only(arr),
        rr=_read_only(rr),
        rrr=_read_only(1.0 - rr),
        p_values=_read_only(p_values),
        zero_event_cell_count=int(zero_event.sum()),
        zero_denominator_count=int(invalid.sum()),
    )


def _read_only(array: FloatArray) -> FloatArray:
    array.setflags(write=False)
    return array


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


def batch_pearson_statistic(
    control_events: npt.ArrayLike,
    control_observed: npt.ArrayLike,
    intervention_events: npt.ArrayLike,
    intervention_observed: npt.ArrayLike,
) -> FloatArray:
    """Pearson X^2 statistic per table (SPEC §7.6); NaN where a denominator is zero.

    Exposed for analyses that rescale the statistic, e.g. the design-effect adjusted
    cluster chi-square (SPEC §14.4).
    """
    c = np.asarray(control_events, dtype=np.float64)
    big_c = np.asarray(control_observed, dtype=np.float64)
    e = np.asarray(intervention_events, dtype=np.float64)
    big_e = np.asarray(intervention_observed, dtype=np.float64)
    invalid = (big_c <= 0) | (big_e <= 0)
    statistic = _batch_x2_statistic(
        c, np.where(invalid, 1.0, big_c), e, np.where(invalid, 1.0, big_e)
    )
    return np.where(invalid, np.nan, statistic)


def summarize_batch(batch: AnalysisBatch, alpha: float) -> SimulationSummary:
    """Summarize per-replicate arrays into SPEC §4.3 summary statistics.

    Undefined replicates (NaN, e.g. zero observed denominators) are excluded from means,
    medians, and percentiles. A NaN p-value never counts as a rejection, so replicates
    without an analyzable table reduce power rather than crash it.
    """
    cer = _defined(batch.cer)
    eer = _defined(batch.eer)
    arr = _defined(batch.arr)
    defined_rr = _defined(batch.rr)
    n = batch.arr.size
    with np.errstate(invalid="ignore"):  # NaN p-values compare False, by design
        power = float(np.mean(batch.p_values < alpha))
    benefit = arr[arr > 0.0]
    harm = arr[arr < 0.0]
    return SimulationSummary(
        mean_cer=float(cer.mean()) if cer.size else math.nan,
        mean_eer=float(eer.mean()) if eer.size else math.nan,
        mean_arr=float(arr.mean()) if arr.size else math.nan,
        mean_rr=float(defined_rr.mean()) if defined_rr.size else None,
        mean_rrr=float(1.0 - defined_rr.mean()) if defined_rr.size else None,
        median_arr=float(np.median(arr)) if arr.size else math.nan,
        ci95_arr_empirical=(
            (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))
            if arr.size
            else (math.nan, math.nan)
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


def _defined(array: FloatArray) -> FloatArray:
    return array[~np.isnan(array)]


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
