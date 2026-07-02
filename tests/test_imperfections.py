"""Imperfection simulation engine (SPEC §6.2, AXIOMS §8-§10).

Three layers of evidence:
1. Semantic pins — degenerate scenarios where §6.2 dictates the observed rate exactly
   (crossover precedence, untreated exposure, loss exclusion, lost-risk multiplier,
   ascertainment, marginal preservation when lost are included).
2. Distributional equivalence — the vectorized engine must match the literal
   per-participant reference model (tests/reference_model.py) in means AND variances,
   at more than one seed (SPEC §6.3 seed-invariant distributional property tests).
3. Operating characteristics — pragmatic imperfections reduce power vs the ideal trial.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from icebergsim.simulate import simulate_trial
from reference_model import simulate_reference_tables
from trial_builders import make_validated

S = 20000  # replicates for stochastic assertions


def pragmatic(
    control: dict[str, Any], intervention: dict[str, Any], **overrides: Any
) -> Any:
    return make_validated(
        n_simulations=overrides.pop("n_simulations", S),
        imperfections={"control": control, "intervention": intervention},
        **overrides,
    )


# --- 1. semantic pins -----------------------------------------------------------------------


def test_crossover_takes_precedence_over_noncompliance() -> None:
    """Everyone crosses AND is noncompliant -> crossover wins: arms swap event rates."""
    both = {"crossover_probability": 1.0, "noncompliance_probability": 1.0}
    result = simulate_trial(pragmatic(both, both))
    assert math.isclose(result.summary.mean_cer, 0.10, abs_tol=0.005)  # p_intervention
    assert math.isclose(result.summary.mean_eer, 0.20, abs_tol=0.005)  # p_control


def test_full_noncompliance_gives_untreated_rate_in_both_arms() -> None:
    noncompliant = {"noncompliance_probability": 1.0}
    result = simulate_trial(pragmatic(noncompliant, noncompliant))
    assert math.isclose(result.summary.mean_cer, 0.30, abs_tol=0.005)  # p_untreated
    assert math.isclose(result.summary.mean_eer, 0.30, abs_tol=0.005)


def test_loss_shrinks_observed_denominators() -> None:
    result = simulate_trial(pragmatic({"loss_probability": 0.25}, {}))
    # n_control = 200, 25% lost -> mean observed denominator 150; intervention untouched.
    assert math.isclose(float(result.tables.control_observed.mean()), 150.0, abs_tol=1.0)
    assert np.all(result.tables.intervention_observed == 200)
    # RR_lost = 1 -> non-lost rate equals the marginal rate.
    assert math.isclose(result.summary.mean_cer, 0.20, abs_tol=0.005)


def test_lost_risk_multiplier_shifts_observed_rate_to_p_nonlost() -> None:
    """SPEC §5.3 canonical values: p=0.2, L=0.25, RR=2 -> p_nonlost = 0.1333..."""
    result = simulate_trial(
        pragmatic({"loss_probability": 0.25, "lost_event_risk_ratio": 2.0}, {})
    )
    assert math.isclose(result.summary.mean_cer, 0.13333333, abs_tol=0.005)


def test_including_lost_in_denominator_recovers_marginal_rate() -> None:
    """AXIOMS §8: with lost included and ascertained, the marginal rate is preserved."""
    result = simulate_trial(
        pragmatic(
            {"loss_probability": 0.25, "lost_event_risk_ratio": 2.0},
            {},
            analysis={"include_lost_in_denominator": True},
        )
    )
    assert np.all(result.tables.control_observed == 200)  # everyone stays in
    assert math.isclose(result.summary.mean_cer, 0.20, abs_tol=0.005)


def test_ascertainment_mixes_true_and_false_positive_rates() -> None:
    imperfect_ascertainment = {
        "ascertainment_event_probability": 0.8,
        "ascertainment_nonevent_false_positive_probability": 0.1,
    }
    result = simulate_trial(pragmatic(imperfect_ascertainment, {}))
    expected = 0.8 * 0.20 + 0.1 * 0.80  # observed = asc_e*p + asc_fp*(1-p)
    assert math.isclose(result.summary.mean_cer, expected, abs_tol=0.005)
    assert math.isclose(result.summary.mean_eer, 0.10, abs_tol=0.005)


def test_lost_risk_derivation_combines_with_ascertainment_in_order() -> None:
    """§6.2 ordering: latent event from p_nonlost FIRST, ascertainment AFTER (AXIOMS §10).

    Applying ascertainment to the marginal rate instead would give 0.8*0.2 + 0.1*0.8 = 0.24;
    the correct order gives 0.8*p_nonlost + 0.1*(1-p_nonlost) with p_nonlost = 0.1333...
    """
    result = simulate_trial(
        pragmatic(
            {
                "loss_probability": 0.25,
                "lost_event_risk_ratio": 2.0,
                "ascertainment_event_probability": 0.8,
                "ascertainment_nonevent_false_positive_probability": 0.1,
            },
            {},
        )
    )
    p_nonlost = (0.20 - 0.25 * 0.40) / 0.75
    expected = 0.8 * p_nonlost + 0.1 * (1.0 - p_nonlost)
    assert math.isclose(result.summary.mean_cer, expected, abs_tol=0.005)


def test_total_loss_replicates_are_warned_and_excluded() -> None:
    """SPEC §3.3: all-lost arms give null replicates with a diagnostic, not NaN poisoning."""
    result = simulate_trial(
        pragmatic(
            {"loss_probability": 0.9},
            {"loss_probability": 0.9},
            allocation={"total_n": 8, "intervention_fraction": 0.5},
            n_simulations=2000,
        )
    )
    assert any(w.startswith("zero_denominator_replicates:") for w in result.warnings)
    assert not math.isnan(result.summary.mean_cer)  # summaries exclude null replicates
    assert not math.isnan(result.summary.mean_arr)
    assert 0.0 <= result.summary.power <= 1.0


def test_precedence_note_is_stated_in_outputs() -> None:
    """AXIOMS §9: the crossover-over-noncompliance precedence must be stated in outputs."""
    result = simulate_trial(
        pragmatic({"crossover_probability": 0.1, "noncompliance_probability": 0.1}, {})
    )
    assert any("precedence" in note for note in result.notes)


def test_imperfect_simulation_is_seed_reproducible() -> None:
    spec = {"loss_probability": 0.1, "noncompliance_probability": 0.2}
    a = simulate_trial(pragmatic(spec, spec, n_simulations=2000, random_seed=555))
    b = simulate_trial(pragmatic(spec, spec, n_simulations=2000, random_seed=555))
    assert np.array_equal(a.tables.control_events, b.tables.control_events)
    assert np.array_equal(a.tables.control_observed, b.tables.control_observed)
    assert np.array_equal(a.arrays.p_values, b.arrays.p_values)


# --- 2. distributional equivalence with the per-participant reference (SPEC §6.3) -----------

RICH_CONTROL = {
    "loss_probability": 0.15,
    "lost_event_risk_ratio": 1.5,
    "noncompliance_probability": 0.10,
    "crossover_probability": 0.05,
    "ascertainment_event_probability": 0.90,
    "ascertainment_nonevent_false_positive_probability": 0.02,
}
RICH_INTERVENTION = {
    "loss_probability": 0.10,
    "lost_event_risk_ratio": 1.2,
    "noncompliance_probability": 0.25,
    "crossover_probability": 0.03,
    "ascertainment_event_probability": 0.85,
    "ascertainment_nonevent_false_positive_probability": 0.01,
}


@pytest.mark.parametrize("seed", [11, 22])
@pytest.mark.parametrize("include_lost", [False, True])
def test_engine_matches_reference_model_distribution(seed: int, include_lost: bool) -> None:
    validated = pragmatic(
        RICH_CONTROL,
        RICH_INTERVENTION,
        random_seed=seed,
        analysis={"include_lost_in_denominator": include_lost},
    )
    engine = simulate_trial(validated).tables
    reference = simulate_reference_tables(validated, seed=seed + 1000, n_sims=S)
    for name, engine_array in (
        ("control_events", engine.control_events),
        ("control_observed", engine.control_observed),
        ("intervention_events", engine.intervention_events),
        ("intervention_observed", engine.intervention_observed),
    ):
        ref_array = reference[name]
        # Means agree within Monte Carlo error (counts of order 200, sd of order 6:
        # 4*sd*sqrt(2/S) is about 0.25; 0.5 leaves slack without hiding real bias).
        assert math.isclose(float(engine_array.mean()), float(ref_array.mean()), abs_tol=0.5), (
            f"{name}: mean {engine_array.mean():.3f} vs reference {ref_array.mean():.3f}"
        )
        # Variances agree within 10%. The legacy deterministic expected-partition model
        # (SPEC §6.4) is caught primarily through the denominator variance (its
        # denominators are deterministic, variance 0); the events variance and the joint
        # correlation below close the gap for marginal-preserving hybrid mutants.
        engine_var, ref_var = float(engine_array.var()), float(ref_array.var())
        if ref_var > 0:
            assert abs(engine_var / ref_var - 1.0) < 0.10, (
                f"{name}: var {engine_var:.2f} vs reference {ref_var:.2f}"
            )
        else:
            assert engine_var == 0.0
    # Joint law check (SPEC §6.3 demands full distributional equivalence, not marginals):
    # the correlation between events and denominators must match the reference model.
    for events, denominators, ref_events, ref_denominators in (
        (
            engine.control_events,
            engine.control_observed,
            reference["control_events"],
            reference["control_observed"],
        ),
        (
            engine.intervention_events,
            engine.intervention_observed,
            reference["intervention_events"],
            reference["intervention_observed"],
        ),
    ):
        if float(denominators.var()) == 0.0:
            assert float(ref_denominators.var()) == 0.0
            continue
        engine_corr = float(np.corrcoef(events, denominators)[0, 1])
        ref_corr = float(np.corrcoef(ref_events, ref_denominators)[0, 1])
        assert math.isclose(engine_corr, ref_corr, abs_tol=0.05), (
            f"events-denominator correlation {engine_corr:.3f} vs reference {ref_corr:.3f}"
        )


# --- 3. operating characteristics ------------------------------------------------------------


def test_pragmatic_imperfections_reduce_power() -> None:
    ideal = simulate_trial(make_validated(n_simulations=10000, random_seed=4242))
    worse = simulate_trial(
        pragmatic(
            {
                "loss_probability": 0.10,
                "noncompliance_probability": 0.05,
                "crossover_probability": 0.02,
            },
            {
                "loss_probability": 0.10,
                "noncompliance_probability": 0.20,
                "crossover_probability": 0.02,
            },
            n_simulations=10000,
            random_seed=4242,
        )
    )
    assert worse.summary.power < ideal.summary.power
