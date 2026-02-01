from __future__ import annotations

import networkx as nx

from smartflow.core.graph_analysis import has_cycle_dfs_recursive, reachable_nodes_dfs_recursive


def test_reachable_nodes_dfs_recursive() -> None:
    g = nx.DiGraph()
    g.add_edges_from([
        ("A", "B"),
        ("B", "C"),
        ("A", "D"),
        ("D", "E"),
    ])

    assert reachable_nodes_dfs_recursive(g, "A") == {"A", "B", "C", "D", "E"}
    assert reachable_nodes_dfs_recursive(g, "C") == {"C"}


def test_has_cycle_dfs_recursive() -> None:
    acyclic = nx.DiGraph()
    acyclic.add_edges_from([("A", "B"), ("B", "C")])
    assert has_cycle_dfs_recursive(acyclic) is False

    cyclic = nx.DiGraph()
    cyclic.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
    assert has_cycle_dfs_recursive(cyclic) is True
