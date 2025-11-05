"""Input configuration loaders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file into a Python dictionary."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_scenario(path: Path) -> Dict[str, Any]:
    """Load a simulation scenario configuration."""

    data = load_json(path)
    required_keys = {"random_seed", "tick_seconds", "transition_window_s", "periods"}
    missing = required_keys.difference(data)
    if missing:
        raise ValueError(f"Scenario file missing keys: {', '.join(sorted(missing))}")
    return data
