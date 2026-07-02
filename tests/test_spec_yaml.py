"""Run every canonical case from spec/tests.yaml as a first-class pytest case."""

from __future__ import annotations

import pytest

from spec_adapters import ADAPTERS
from spec_harness import SpecCase, check_case, default_absolute_tolerance, load_cases

DEFAULT_TOL = default_absolute_tolerance()


@pytest.mark.parametrize("spec_case", load_cases(), ids=lambda c: c.id)
def test_spec_case(spec_case: SpecCase) -> None:
    adapter = ADAPTERS.get((spec_case.module, spec_case.function))
    if adapter is None:
        pytest.xfail(f"{spec_case.module}.{spec_case.function} not implemented yet")
    actual = adapter(spec_case.case["input"])
    check_case(spec_case.case, actual, DEFAULT_TOL)
