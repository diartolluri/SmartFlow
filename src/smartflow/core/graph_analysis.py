"""Graph analytics utilities for NEA evidence.

This module intentionally contains a small amount of "from scratch" graph traversal
(to evidence graph skills), even though NetworkX is used elsewhere.

Features:
- Connected components via BFS (ignoring direction)
- Edge betweenness centrality (NetworkX)
- Critical-edge ranking by combining centrality with observed congestion metrics
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

import networkx as nx


def reachable_nodes_dfs_recursive(graph: nx.DiGraph, start: str) -> Set[str]:
    """Return the set of nodes reachable from `start` via directed edges.

    NEA evidence:
        This is an explicit *recursive* depth-first search (DFS) implementation.
    """

    start_s = str(start)
    visited: Set[str] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        for nbr in graph.successors(node):
            sn = str(nbr)
            if sn not in visited:
                dfs(sn)

    if start_s in graph:
        dfs(start_s)
    return visited


def has_cycle_dfs_recursive(graph: nx.DiGraph) -> bool:
    """Detect whether a directed graph contains a cycle using recursive DFS."""

    visited: Set[str] = set()
    in_stack: Set[str] = set()

    def visit(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for nbr in graph.successors(node):
            sn = str(nbr)
            if sn not in visited:
                if visit(sn):
                    return True
            elif sn in in_stack:
                return True
        in_stack.remove(node)
        return False

    for n in graph.nodes:
        sn = str(n)
        if sn not in visited:
            if visit(sn):
                return True
    return False


def weak_components_bfs(graph: nx.DiGraph) -> List[Set[str]]:
    """Return weakly-connected components using an explicit BFS traversal."""

    # Build undirected adjacency without materialising a full nx.Graph.
    adj: Dict[str, Set[str]] = {str(n): set() for n in graph.nodes}
    for u, v in graph.edges:
        su, sv = str(u), str(v)
        adj.setdefault(su, set()).add(sv)
        adj.setdefault(sv, set()).add(su)

    seen: Set[str] = set()
    components: List[Set[str]] = []

    for start in adj.keys():
        if start in seen:
            continue
        q: deque[str] = deque([start])
        comp: Set[str] = set()
        seen.add(start)

        while q:
            node = q.popleft()
            comp.add(node)
            for nbr in adj.get(node, ()):  # BFS traversal
                if nbr not in seen:
                    seen.add(nbr)
                    q.append(nbr)

        components.append(comp)

    return components


def edge_betweenness(graph: nx.DiGraph) -> Dict[Tuple[str, str], float]:
    """Compute edge betweenness centrality on the directed graph."""

    scores = nx.edge_betweenness_centrality(graph, normalized=True)
    return {(str(u), str(v)): float(s) for (u, v), s in scores.items()}


def articulation_points(graph: nx.DiGraph) -> List[str]:
    """Return articulation points on the underlying undirected graph."""

    ug = nx.Graph()
    ug.add_nodes_from(graph.nodes)
    ug.add_edges_from(graph.edges)
    return [str(n) for n in nx.articulation_points(ug)]


@dataclass(frozen=True)
class EdgeCriticality:
    edge: Tuple[str, str]
    betweenness: float
    peak_occupancy: float
    peak_queue: int
    score: float


def rank_critical_edges(
    graph: nx.DiGraph,
    *,
    edge_metrics: Mapping[str, object] | None = None,
    edge_id_for_uv: Mapping[Tuple[str, str], str] | None = None,
    top_k: int = 10,
) -> List[EdgeCriticality]:
    """Rank edges by a combined structural + observed congestion score.

    Args:
        graph: Layout graph.
        edge_metrics: MetricsCollector.edge_metrics mapping (edge_id -> EdgeMetrics).
        edge_id_for_uv: Optional mapping from (u,v) to edge_id used in metrics.
        top_k: How many to return.

    Returns:
        Sorted list of edges with a computed score.
    """

    between = edge_betweenness(graph)

    def get_metric(edge_id: str, name: str, default):
        if not edge_metrics:
            return default
        m = edge_metrics.get(edge_id)
        if m is None:
            return default
        return getattr(m, name, default)

    ranked: List[EdgeCriticality] = []
    for u, v in graph.edges:
        su, sv = str(u), str(v)
        b = float(between.get((su, sv), 0.0))
        edge_id = None
        if edge_id_for_uv is not None:
            edge_id = edge_id_for_uv.get((su, sv))
        if edge_id is None:
            # Fall back to the edge attribute 'id' if present.
            data = graph.get_edge_data(u, v) or {}
            edge_id = str(data.get("id", f"{su}->{sv}"))

        peak_occ = float(get_metric(edge_id, "peak_occupancy", 0.0))
        queue_over_time = get_metric(edge_id, "queue_length_over_time", [])
        peak_q = int(max(queue_over_time) if queue_over_time else 0)

        # Simple combined score (defensible + easy to explain):
        # centrality contributes to structural importance; congestion contributes to observed strain.
        score = (1.5 * b) + (0.05 * peak_occ) + (0.02 * peak_q)
        ranked.append(
            EdgeCriticality(
                edge=(su, sv),
                betweenness=b,
                peak_occupancy=peak_occ,
                peak_queue=peak_q,
                score=float(score),
            )
        )

    ranked.sort(key=lambda e: e.score, reverse=True)
    return ranked[: max(0, int(top_k))]
