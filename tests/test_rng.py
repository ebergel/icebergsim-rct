"""Randomness layer (ARCHITECTURE §3.3): reproducible, named-algorithm, independent streams."""

from __future__ import annotations

import numpy as np

from icebergsim.rng import RNG_ALGORITHM, create_rng


def test_same_seed_and_stream_reproduce_identical_draws() -> None:
    a = create_rng(777, "main").binomial(100, 0.3, size=50)
    b = create_rng(777, "main").binomial(100, 0.3, size=50)
    assert np.array_equal(a, b)


def test_different_stream_names_give_independent_streams() -> None:
    a = create_rng(777, "main").binomial(100, 0.3, size=50)
    b = create_rng(777, "null").binomial(100, 0.3, size=50)
    assert not np.array_equal(a, b)


def test_different_seeds_diverge() -> None:
    a = create_rng(1, "main").binomial(100, 0.3, size=50)
    b = create_rng(2, "main").binomial(100, 0.3, size=50)
    assert not np.array_equal(a, b)


def test_algorithm_is_named_and_used() -> None:
    assert RNG_ALGORITHM == "PCG64"
    rng = create_rng(1, "main")
    assert type(rng.bit_generator).__name__ == RNG_ALGORITHM


def test_none_seed_is_allowed() -> None:
    rng = create_rng(None, "main")
    draws = rng.binomial(10, 0.5, size=5)
    assert draws.shape == (5,)
