"""Tests for floorplan parsing."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import pytest

def test_load_floorplan(tmp_path: Path) -> None:
    floorplan = import_module("smartflow.core.floorplan")
    
    # Create a dummy JSON
    json_content = """
    {
        "nodes": [{"id": "A", "pos": [0,0,0], "from": "A", "to": "A"}, {"id": "B", "pos": [10,0,0], "from": "B", "to": "B"}],
        "edges": [{"id": "e1", "from": "A", "to": "B", "length_m": 10.0, "width_m": 2.0}]
    }
    """
    # Note: Added dummy from/to in nodes just in case validation is strict, though usually not needed for nodes.
    # Actually nodes don't have from/to.
    
    json_content = """
    {
        "nodes": [{"id": "A", "pos": [0,0,0]}, {"id": "B", "pos": [10,0,0]}],
        "edges": [{"id": "e1", "from": "A", "to": "B", "length_m": 10.0, "width_m": 2.0}]
    }
    """
    
    sample = tmp_path / "plan.json"
    sample.write_text(json_content, encoding="utf-8")
    
    fp = floorplan.load_floorplan(sample)
    assert len(fp.nodes) == 2
    assert len(fp.edges) == 1
    
    # Test graph conversion (should auto-generate reverse edge)
    graph = fp.to_networkx()
    assert graph.has_edge("A", "B")
    assert graph.has_edge("B", "A") # The fix I implemented!
