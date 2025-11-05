"""Tests for floorplan parsing (placeholders)."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


def test_load_floorplan_not_implemented(tmp_path: Path) -> None:
    sample = tmp_path / "plan.json"
    sample.write_text("{}", encoding="utf-8")
    floorplan = import_module("smartflow.core.floorplan")

    try:
        floorplan.load_floorplan(sample)
    except NotImplementedError:
        pass
    else:
        raise AssertionError("load_floorplan should be implemented during development")
