"""Definition file loading. YAML is a superset of JSON, so one loader covers both."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_definition(path: Path | str) -> Any:
    """Load a YAML or JSON definition file into a raw mapping. Validation is separate."""
    with Path(path).open() as f:
        return yaml.safe_load(f)
