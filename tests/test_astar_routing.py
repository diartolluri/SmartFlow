"""Test A* routing returns optimal paths identical to Dijkstra."""

import networkx as nx
import pytest

from smartflow.core.routing import (
    compute_a_star_path,
    compute_shortest_path,
)


def _build_test_graph() -> nx.DiGraph:
    """Create a small test graph with positions for heuristic calculation."""
    g = nx.DiGraph()
    # Nodes with x/y positions (Euclidean heuristic can be used)
    g.add_node("A", position=(0.0, 0.0))
    g.add_node("B", position=(10.0, 0.0))
    g.add_node("C", position=(5.0, 8.0))
    g.add_node("D", position=(20.0, 0.0))

    # Edges with length_m and width_m for cost calculation
    g.add_edge("A", "B", length_m=10.0, width_m=2.0)
    g.add_edge("A", "C", length_m=9.5, width_m=2.0)
    g.add_edge("B", "D", length_m=10.0, width_m=2.0)
    g.add_edge("C", "D", length_m=16.0, width_m=2.0)  # Longer path via C
    g.add_edge("C", "B", length_m=9.0, width_m=2.0)

    return g


def test_astar_matches_dijkstra():
    """A* should return the same optimal path as Dijkstra."""
    g = _build_test_graph()

    dijkstra_path = compute_shortest_path(g, "A", "D")
    astar_path = compute_a_star_path(g, "A", "D", heuristic="euclidean")

    # Both should find the same optimal path
    assert list(dijkstra_path) == list(astar_path), (
        f"Dijkstra: {dijkstra_path}, A*: {astar_path}"
    )


def test_astar_with_zero_heuristic():
    """A* with zero heuristic should behave like Dijkstra."""
    g = _build_test_graph()

    dijkstra_path = compute_shortest_path(g, "A", "D")
    astar_zero = compute_a_star_path(g, "A", "D", heuristic="zero")

    assert list(dijkstra_path) == list(astar_zero)


def test_astar_with_auto_heuristic():
    """A* with 'auto' should pick Euclidean when positions are present."""
    g = _build_test_graph()

    # Auto should detect positions and use Euclidean
    astar_auto = compute_a_star_path(g, "A", "D", heuristic="auto")
    astar_euclidean = compute_a_star_path(g, "A", "D", heuristic="euclidean")

    assert list(astar_auto) == list(astar_euclidean)


def test_astar_with_stairs_penalty():
    """A* should respect stairs penalty the same as Dijkstra."""
    g = _build_test_graph()
    # Mark B->D as stairs
    g.edges["B", "D"]["is_stairs"] = True

    dijkstra_path = compute_shortest_path(g, "A", "D", stairs_penalty=50.0)
    astar_path = compute_a_star_path(g, "A", "D", stairs_penalty=50.0, heuristic="euclidean")

    # With heavy stairs penalty, both should avoid B->D and go via C
    assert list(dijkstra_path) == list(astar_path)
