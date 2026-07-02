"""Load spec/tests.yaml (the canonical Phoenix tests) and check results against expectations.

Case shape (see spec/tests.yaml):
- ``input``: passed verbatim to the registered adapter for (module, function).
- ``output``: exact expectations, compared with per-key ``tolerance`` or the default.
- ``output_constraints``: bound checks — keys ending in ``_between`` / ``_less_than`` /
  ``_greater_than``, or bare boolean flags the adapter must report.
- ``error``: the adapter must report a structured error with matching type/code/message.
- ``warnings_contains``: strings that must appear among reported warnings.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SPEC_TESTS_PATH = Path(__file__).resolve().parent.parent / "spec" / "tests.yaml"

# An adapter takes a case's ``input`` mapping and returns an "actual" mapping whose keys
# cover the case's expectations. Error cases return {"error": {"type": ..., "code": ...,
# "message": ...}}; warning-producing cases include {"warnings": [...]}.
Adapter = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class SpecCase:
    module: str
    function: str
    name: str
    case: Mapping[str, Any]

    @property
    def id(self) -> str:
        return f"{self.module}/{self.function}/{self.name}"


def load_spec() -> Mapping[str, Any]:
    with SPEC_TESTS_PATH.open() as f:
        loaded: Mapping[str, Any] = yaml.safe_load(f)
    return loaded


def load_cases() -> list[SpecCase]:
    spec = load_spec()
    return [
        SpecCase(module=module, function=function, name=case["name"], case=case)
        for module, functions in spec["modules"].items()
        for function, cases in functions.items()
        for case in cases
    ]


def load_property_test_names() -> list[str]:
    return [prop["name"] for prop in load_spec()["property_tests"]]


def default_absolute_tolerance() -> float:
    return float(load_spec()["metadata"]["tolerance_defaults"]["absolute"])


def check_case(case: Mapping[str, Any], actual: Mapping[str, Any], default_tol: float) -> None:
    if "error" in case:
        _check_error(case["error"], actual)
    if "output" in case:
        _check_output(case["output"], case.get("tolerance", {}), actual, default_tol)
    if "output_constraints" in case:
        _check_constraints(case["output_constraints"], actual)
    if "warnings_contains" in case:
        _check_warnings(case["warnings_contains"], actual)


def _check_error(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    assert "error" in actual, f"expected error {expected}, got success: {actual}"
    error = actual["error"]
    assert error["type"] == expected["type"], f"error type: {error} != {expected}"
    if "code" in expected:
        assert error["code"] == expected["code"], f"error code: {error} != {expected}"
    if "message_contains" in expected:
        assert expected["message_contains"] in error["message"], (
            f"error message {error['message']!r} does not contain "
            f"{expected['message_contains']!r}"
        )


def _check_output(
    expected: Mapping[str, Any],
    tolerances: Mapping[str, float],
    actual: Mapping[str, Any],
    default_tol: float,
) -> None:
    # Outputs may coexist with warnings, never with errors.
    assert "error" not in actual, f"expected success, got error: {actual['error']}"
    for key, expected_value in expected.items():
        assert key in actual, f"missing output key {key!r} in {sorted(actual)}"
        tol = float(tolerances.get(key, default_tol))
        _assert_close(actual[key], expected_value, tol, path=key)


def _assert_close(actual: Any, expected: Any, tol: float, path: str) -> None:
    if expected is None:
        assert actual is None, f"{path}: expected null, got {actual!r}"
    elif isinstance(expected, bool):
        assert actual is expected, f"{path}: expected {expected}, got {actual!r}"
    elif isinstance(expected, int | float):
        assert actual is not None, f"{path}: expected {expected}, got null"
        assert math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tol), (
            f"{path}: |{actual} - {expected}| > {tol}"
        )
    elif isinstance(expected, str):
        assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"
    elif isinstance(expected, Sequence):
        assert isinstance(actual, Sequence), f"{path}: expected sequence, got {actual!r}"
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_close(a, e, tol, path=f"{path}[{i}]")
    else:  # pragma: no cover - no other types appear in spec/tests.yaml
        raise TypeError(f"{path}: unsupported expected value {expected!r}")


def _check_constraints(constraints: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    assert "error" not in actual, f"expected success, got error: {actual['error']}"
    for key, bound in constraints.items():
        if key.endswith("_between"):
            value = _get(actual, key.removesuffix("_between"))
            low, high = bound
            assert low <= value <= high, f"{key}: {value} not in [{low}, {high}]"
        elif key.endswith("_less_than"):
            value = _get(actual, key.removesuffix("_less_than"))
            assert value < bound, f"{key}: {value} >= {bound}"
        elif key.endswith("_greater_than"):
            value = _get(actual, key.removesuffix("_greater_than"))
            assert value > bound, f"{key}: {value} <= {bound}"
        else:
            # Bare flags, e.g. pragmatic_power_less_than_ideal_power: true — the adapter
            # computes the comparison and reports the boolean under the same key.
            assert _get(actual, key) is bound, f"{key}: expected {bound}, got {_get(actual, key)}"


def _check_warnings(expected_substrings: Sequence[str], actual: Mapping[str, Any]) -> None:
    warnings = actual.get("warnings", [])
    for substring in expected_substrings:
        assert any(substring in w for w in warnings), (
            f"no warning containing {substring!r} in {warnings}"
        )


def _get(actual: Mapping[str, Any], key: str) -> Any:
    assert key in actual, f"missing key {key!r} in {sorted(actual)}"
    return actual[key]
