"""Registry mapping spec/tests.yaml (module, function) pairs to implementation adapters.

Each adapter is a thin, logic-free bridge: it unpacks the case's ``input`` mapping, calls the
real icebergsim function, and repacks the result under the keys the spec expects. Statistical
logic belongs in src/icebergsim/, never here.

Adapters are registered step by step as modules are implemented; cases without an adapter
are reported as xfail by tests/test_spec_yaml.py.
"""

from __future__ import annotations

from spec_harness import Adapter

ADAPTERS: dict[tuple[str, str], Adapter] = {}
