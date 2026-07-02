"""Property tests named in spec/tests.yaml.

Each named property is implemented in the step that builds the module it exercises; until
then it is collected and reported as xfail so coverage of the canonical list stays visible.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from icebergsim.simulate import simulate_trial
from spec_harness import load_property_test_names
from trial_builders import make_validated

STOCHASTIC_POWER_TOLERANCE = 0.03  # spec/tests.yaml metadata.tolerance_defaults


def check_probabilities_are_bounded() -> None:
    """All reported probabilities are in [0,1] or null with a warning."""
    result = simulate_trial(make_validated(n_simulations=2000), include_type_i_error=True)
    summary = result.summary
    for value in (
        summary.mean_cer,
        summary.mean_eer,
        summary.power,
        summary.power_mcse,
        summary.type_i_error,
        summary.type_i_error_mcse,
    ):
        assert value is not None and 0.0 <= value <= 1.0
    assert np.all((result.arrays.p_values >= 0.0) & (result.arrays.p_values <= 1.0))
    assert np.all((result.arrays.cer >= 0.0) & (result.arrays.cer <= 1.0))
    assert np.all((result.arrays.eer >= 0.0) & (result.arrays.eer <= 1.0))
    assert np.all((result.arrays.arr >= -1.0) & (result.arrays.arr <= 1.0))


def check_monotonic_power_with_sample_size() -> None:
    """Power is nondecreasing in total_n, within Monte Carlo tolerance."""
    powers = [
        simulate_trial(
            make_validated(
                n_simulations=4000,
                random_seed=31415,
                allocation={"total_n": total_n, "intervention_fraction": 0.5},
            )
        ).summary.power
        for total_n in (100, 400, 1600)
    ]
    for smaller, larger in zip(powers, powers[1:], strict=False):
        assert larger >= smaller - STOCHASTIC_POWER_TOLERANCE


def check_null_type_i_error_near_alpha() -> None:
    """Under p_control == p_intervention, Type I error is near alpha."""
    result = simulate_trial(
        make_validated(n_simulations=10000, random_seed=271828), include_type_i_error=True
    )
    assert result.summary.type_i_error is not None
    assert abs(result.summary.type_i_error - 0.05) <= STOCHASTIC_POWER_TOLERANCE


IMPLEMENTED: dict[str, Callable[[], None]] = {
    "probabilities_are_bounded": check_probabilities_are_bounded,
    "monotonic_power_with_sample_size": check_monotonic_power_with_sample_size,
    "null_type_i_error_near_alpha": check_null_type_i_error_near_alpha,
}


@pytest.mark.parametrize("name", load_property_test_names())
def test_spec_property(name: str) -> None:
    check = IMPLEMENTED.get(name)
    if check is None:
        pytest.xfail(f"property test {name!r} not implemented yet")
    check()
