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

import numpy as np
from scipy import stats

from icebergsim.model import AnalysisResult, Table2x2

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
