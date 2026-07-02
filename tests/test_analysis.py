"""Analysis of a single 2x2 table (SPEC §7).

Formula tests recompute the spec formulas independently inside the test, so the
implementation is checked against SPEC §7 itself, not against its own output.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from scipy import stats

from icebergsim.analysis import analyze_2x2, analyze_2x2_batch
from icebergsim.model import Table2x2
from icebergsim.rng import create_rng

Z95 = 1.959963984540054  # Phi^-1(0.975)

# Canonical table: 40/200 control events vs 20/200 intervention events (SPEC tests.yaml).
TABLE = Table2x2(
    control_events=40, control_observed=200, intervention_events=20, intervention_observed=200
)


def test_effect_measures_canonical_table() -> None:
    result = analyze_2x2(TABLE)
    assert result.cer == 0.20
    assert result.eer == 0.10
    assert result.arr is not None and math.isclose(result.arr, 0.10, abs_tol=1e-12)
    assert result.rr is not None and math.isclose(result.rr, 0.50, abs_tol=1e-12)
    assert result.rrr is not None and math.isclose(result.rrr, 0.50, abs_tol=1e-12)
    assert result.nnt is not None and math.isclose(result.nnt, 10.0, abs_tol=1e-12)
    assert result.nnh is None


def test_harm_direction_swaps_nnt_for_nnh() -> None:
    result = analyze_2x2(
        Table2x2(
            control_events=20,
            control_observed=200,
            intervention_events=40,
            intervention_observed=200,
        )
    )
    assert result.arr is not None and math.isclose(result.arr, -0.10, abs_tol=1e-12)
    assert result.rr is not None and math.isclose(result.rr, 2.0, abs_tol=1e-12)
    assert result.rrr is not None and math.isclose(result.rrr, -1.0, abs_tol=1e-12)
    assert result.nnt is None
    assert result.nnh is not None and math.isclose(result.nnh, 10.0, abs_tol=1e-12)


def test_wald_arr_ci_matches_spec_7_3_formula() -> None:
    result = analyze_2x2(TABLE, alpha=0.05)
    se = math.sqrt(0.20 * 0.80 / 200 + 0.10 * 0.90 / 200)
    assert result.arr_ci is not None
    assert math.isclose(result.arr_ci[0], 0.10 - Z95 * se, abs_tol=1e-9)
    assert math.isclose(result.arr_ci[1], 0.10 + Z95 * se, abs_tol=1e-9)


def test_log_rr_ci_matches_spec_7_4_formula() -> None:
    result = analyze_2x2(TABLE, alpha=0.05)
    se = math.sqrt(1 / 20 - 1 / 200 + 1 / 40 - 1 / 200)
    lo = math.exp(math.log(0.5) - Z95 * se)
    hi = math.exp(math.log(0.5) + Z95 * se)
    assert result.rr_ci is not None
    assert math.isclose(result.rr_ci[0], lo, abs_tol=1e-9)
    assert math.isclose(result.rr_ci[1], hi, abs_tol=1e-9)
    # RRR CI is 1 - reversed RR CI.
    assert result.rrr_ci is not None
    assert math.isclose(result.rrr_ci[0], 1 - hi, abs_tol=1e-9)
    assert math.isclose(result.rrr_ci[1], 1 - lo, abs_tol=1e-9)


def test_likelihood_ratio_p_value_matches_spec_7_5_formula() -> None:
    p_common = 60 / 400
    expected = (200 * p_common, 200 * (1 - p_common), 200 * p_common, 200 * (1 - p_common))
    observed = (40, 160, 20, 180)
    g = 2 * sum(o * math.log(o / exp) for o, exp in zip(observed, expected, strict=True))
    result = analyze_2x2(TABLE, p_value_method="likelihood_ratio")
    assert result.p_value is not None
    assert math.isclose(result.p_value, float(stats.chi2.sf(g, df=1)), abs_tol=1e-12)
    assert result.p_value < 0.01


def test_pearson_p_value_matches_spec_7_6_formula() -> None:
    p_common = 60 / 400
    expected = (200 * p_common, 200 * (1 - p_common), 200 * p_common, 200 * (1 - p_common))
    observed = (40, 160, 20, 180)
    x2 = sum((o - exp) ** 2 / exp for o, exp in zip(observed, expected, strict=True))
    result = analyze_2x2(TABLE, p_value_method="pearson_chi_square")
    assert result.p_value is not None
    assert math.isclose(result.p_value, float(stats.chi2.sf(x2, df=1)), abs_tol=1e-12)


def test_fisher_exact_supported() -> None:
    result = analyze_2x2(TABLE, p_value_method="fisher_exact")
    assert result.p_value is not None
    assert 0.0 < result.p_value < 0.01


def test_equal_event_rates_give_p_value_one() -> None:
    table = Table2x2(
        control_events=20, control_observed=100, intervention_events=20, intervention_observed=100
    )
    result = analyze_2x2(table)
    assert result.p_value == 1.0
    assert result.nnt is None
    assert result.nnh is None
    assert "no_absolute_difference" in result.warnings


def test_zero_event_cell_without_correction_nulls_rr_family() -> None:
    table = Table2x2(
        control_events=0, control_observed=100, intervention_events=5, intervention_observed=100
    )
    result = analyze_2x2(table, zero_cell_correction=None)
    assert result.rr is None
    assert result.rrr is None
    assert result.rr_ci is None
    assert result.rrr_ci is None
    assert "zero_event_cell" in result.warnings
    # ARR does not require division by a zero cell and stays defined.
    assert result.arr is not None and math.isclose(result.arr, -0.05, abs_tol=1e-12)


def test_zero_event_cell_with_correction_uses_corrected_cells() -> None:
    table = Table2x2(
        control_events=0, control_observed=100, intervention_events=5, intervention_observed=100
    )
    result = analyze_2x2(table, zero_cell_correction=0.5)
    # Corrected cells: c=0.5, C=101, e=5.5, E=101 -> RR = 5.5/0.5 = 11.
    assert result.rr is not None and math.isclose(result.rr, 11.0, abs_tol=1e-12)
    assert result.rr_ci is not None
    assert "zero_event_cell" in result.warnings
    assert "zero_cell_correction_applied" in result.warnings
    # Point estimates from uncorrected cells are unaffected.
    assert result.cer == 0.0
    assert result.eer == 0.05


def test_degenerate_all_events_table() -> None:
    table = Table2x2(
        control_events=10, control_observed=10, intervention_events=10, intervention_observed=10
    )
    result = analyze_2x2(table)
    assert result.p_value == 1.0
    assert result.arr == 0.0


def test_unsupported_p_value_method_yields_null_with_warning() -> None:
    result = analyze_2x2(TABLE, p_value_method="monte_carlo_exact")
    assert result.p_value is None
    assert any("p_value_method_unsupported" in w for w in result.warnings)


def test_batch_analysis_matches_scalar_analysis_exactly() -> None:
    """SPEC §6.3: vectorized batch must be exactly equivalent to per-table analysis."""
    rng = create_rng(2024, "batch-equivalence")
    n_tables = 300
    big_c, big_e = 60, 40
    # Low event probability so zero cells genuinely occur in the sample.
    c = rng.binomial(big_c, 0.05, size=n_tables)
    e = rng.binomial(big_e, 0.03, size=n_tables)
    for method in ("likelihood_ratio", "pearson_chi_square"):
        for correction in (0.5, None):
            batch = analyze_2x2_batch(
                control_events=c,
                control_observed=np.full(n_tables, big_c),
                intervention_events=e,
                intervention_observed=np.full(n_tables, big_e),
                p_value_method=method,
                zero_cell_correction=correction,
            )
            assert int(np.isnan(batch.rr).sum()) == (
                batch.zero_event_cell_count if correction is None else 0
            )
            for i in range(n_tables):
                scalar = analyze_2x2(
                    Table2x2(
                        control_events=int(c[i]),
                        control_observed=big_c,
                        intervention_events=int(e[i]),
                        intervention_observed=big_e,
                    ),
                    p_value_method=method,
                    zero_cell_correction=correction,
                )
                assert scalar.p_value is not None
                assert math.isclose(batch.p_values[i], scalar.p_value, abs_tol=1e-12)
                assert scalar.arr is not None
                assert math.isclose(batch.arr[i], scalar.arr, abs_tol=1e-12)
                if scalar.rr is None:
                    assert math.isnan(batch.rr[i])
                else:
                    assert math.isclose(batch.rr[i], scalar.rr, abs_tol=1e-12)


@given(data=st.data())
def test_outputs_are_bounded_and_cis_contain_estimates(data: st.DataObject) -> None:
    control_observed = data.draw(st.integers(1, 150), label="C")
    intervention_observed = data.draw(st.integers(1, 150), label="E")
    control_events = data.draw(st.integers(0, control_observed), label="c")
    intervention_events = data.draw(st.integers(0, intervention_observed), label="e")
    method = data.draw(
        st.sampled_from(["likelihood_ratio", "pearson_chi_square", "fisher_exact"]),
        label="method",
    )
    result = analyze_2x2(
        Table2x2(
            control_events=control_events,
            control_observed=control_observed,
            intervention_events=intervention_events,
            intervention_observed=intervention_observed,
        ),
        p_value_method=method,
    )
    assert result.cer is not None and 0.0 <= result.cer <= 1.0
    assert result.eer is not None and 0.0 <= result.eer <= 1.0
    assert result.arr is not None and -1.0 <= result.arr <= 1.0
    assert result.p_value is not None and 0.0 <= result.p_value <= 1.0
    assert result.arr_ci is not None
    assert result.arr_ci[0] <= result.arr <= result.arr_ci[1]
    if result.rr is not None:
        assert result.rr >= 0.0
        assert result.rr_ci is not None
        assert result.rr_ci[0] <= result.rr <= result.rr_ci[1]
