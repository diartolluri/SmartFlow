"""Tests for routing helpers."""

from importlib import import_module
import networkx as nx

def test_routing() -> None:
    routing = import_module("smartflow.core.routing")
    
    g = nx.DiGraph()
    g.add_edge("A", "B", length_m=10.0)
    g.add_edge("B", "C", length_m=10.0)
    
    path = routing.compute_shortest_path(g, "A", "C")
    assert path == ["A", "B", "C"]
