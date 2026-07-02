"""Randomness layer (ARCHITECTURE §3.3, AXIOMS §3).

Reproducibility contract: the same (seed, stream_name) pair always yields the same stream of
draws within this implementation and RNG algorithm. Distinct stream names derive independent
streams from the same seed, so scenario families, subgroups, and null copies never share or
disturb each other's randomness.
"""

from __future__ import annotations

import hashlib

import numpy as np

RNG_ALGORITHM = "PCG64"


def create_rng(seed: int | None, stream_name: str = "") -> np.random.Generator:
    """Create a reproducible generator for the given seed and named stream.

    A None seed yields fresh OS entropy (explicitly non-reproducible). The stream name is
    hashed with SHA-256 so stream derivation is stable across platforms and sessions.
    """
    if seed is None:
        return np.random.Generator(np.random.PCG64())
    stream_key = int.from_bytes(hashlib.sha256(stream_name.encode()).digest()[:8], "big")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream_key])))
