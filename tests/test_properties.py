"""Property tests named in spec/tests.yaml.

Each named property gets a real hypothesis/pytest implementation in the step that implements
the module it exercises; until then it is collected and reported as xfail so coverage of the
canonical list is always visible.
"""

from __future__ import annotations

import pytest

from spec_harness import load_property_test_names

IMPLEMENTED: dict[str, object] = {}


@pytest.mark.parametrize("name", load_property_test_names())
def test_spec_property(name: str) -> None:
    if name not in IMPLEMENTED:
        pytest.xfail(f"property test {name!r} not implemented yet")
