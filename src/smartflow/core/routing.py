"""Routing and path choice utilities.

This module intentionally keeps the routing API small and deterministic.

NEA note (validity):
- The base edge cost is a simple proxy for travel effort: $\frac{\text{length}}{\text{width}}$.
- For realism, callers may optionally provide a *congestion map* per tick so edge
    costs increase smoothly with crowding (without changing the graph structure).
"""

from __future__ import annotations

import math
import random
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import networkx as nx


def _edge_weight(
    data: dict,
    stairs_penalty: float = 0.0,
    *,
    density_ratio: float = 0.0,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
) -> float:
    """Compute a deterministic edge cost.

    Args:
        data: The edge attribute dictionary from NetworkX.
        stairs_penalty: Additive penalty if the edge represents stairs.
        density_ratio: Dimensionless crowding ratio (0 = empty, 1 = at capacity).
        congestion_alpha: Strength of congestion penalty. 0 disables congestion.
        congestion_p: Exponent controlling how sharply costs rise as density increases.

    Returns:
        A positive float cost (lower is better).

    NEA note (technique):
        We use a smooth, monotonic penalty: cost *= (1 + alpha * density_ratio^p).
        This is easy to justify, test (monotonic), and avoids discontinuities.
    """

    base = data.get("length_m", 1.0) / max(data.get("width_m", 1.0), 0.1)
    if data.get("is_stairs", False):
        base += stairs_penalty

    ratio = max(0.0, float(density_ratio))
    alpha = max(0.0, float(congestion_alpha))
    p = max(0.1, float(congestion_p))
    if alpha > 0.0 and ratio > 0.0:
        base *= 1.0 + alpha * (ratio**p)

    return float(base)


def compute_path_cost(
    graph: nx.DiGraph,
    path: Sequence[str],
    *,
    stairs_penalty: float = 0.0,
    congestion_map: Mapping[Tuple[str, str], float] | None = None,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
) -> float:
    """Compute the total cost of a path.

    This is primarily used for *comparing* two candidate routes deterministically
    (e.g., hysteresis decisions during rerouting).
    """

    if len(path) < 2:
        return 0.0

    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        data = graph.get_edge_data(u, v)
        if not data:
            # If the path is inconsistent with the graph, treat as infinite.
            return float("inf")
        ratio = 0.0
        if congestion_map is not None:
            ratio = float(congestion_map.get((u, v), 0.0))
        total += _edge_weight(
            data,
            stairs_penalty=stairs_penalty,
            density_ratio=ratio,
            congestion_alpha=congestion_alpha,
            congestion_p=congestion_p,
        )
    return float(total)


def compute_shortest_path(
    graph: nx.DiGraph,
    source: str,
    target: str,
    *,
    stairs_penalty: float = 0.0,
    congestion_map: Mapping[Tuple[str, str], float] | None = None,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
) -> Sequence[str]:
    """Return the shortest path between two nodes in the layout graph."""

    return nx.shortest_path(
        graph,
        source=source,
        target=target,
        weight=lambda u, v, data: _edge_weight(
            data,
            stairs_penalty=stairs_penalty,
            density_ratio=(float(congestion_map.get((u, v), 0.0)) if congestion_map is not None else 0.0),
            congestion_alpha=congestion_alpha,
            congestion_p=congestion_p,
        ),
    )


def compute_k_shortest_paths(
    graph: nx.DiGraph,
    source: str,
    target: str,
    *,
    k: int = 3,
    stairs_penalty: float = 0.0,
    congestion_map: Mapping[Tuple[str, str], float] | None = None,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
) -> List[Sequence[str]]:
    """Return a collection of the *k* best routes for diversification."""

    generator = nx.shortest_simple_paths(
        graph,
        source,
        target,
        weight=lambda u, v, data: _edge_weight(
            data,
            stairs_penalty=stairs_penalty,
            density_ratio=(float(congestion_map.get((u, v), 0.0)) if congestion_map is not None else 0.0),
            congestion_alpha=congestion_alpha,
            congestion_p=congestion_p,
        ),
    )
    paths: List[Sequence[str]] = []
    for _ in range(k):
        try:
            paths.append(next(generator))
        except StopIteration:
            break
    return paths


def choose_route(
    paths: Iterable[Sequence[str]], 
    beta: float, 
    graph: nx.DiGraph | None = None,
    rng: random.Random | None = None,
    *,
    stairs_penalty: float = 0.0,
    congestion_map: Mapping[Tuple[str, str], float] | None = None,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
) -> Sequence[str]:
    """Select a route using a softmax-weighted choice model."""

    path_list = list(paths)
    if not path_list:
        raise ValueError("No paths available for selection")
    if len(path_list) == 1 or beta >= 10_000:
        return path_list[0]

    # Calculate costs: if graph provided, use sum of edge weights, else hop count
    costs = []
    if graph:
        for path in path_list:
            costs.append(
                compute_path_cost(
                    graph,
                    path,
                    stairs_penalty=stairs_penalty,
                    congestion_map=congestion_map,
                    congestion_alpha=congestion_alpha,
                    congestion_p=congestion_p,
                )
            )
    else:
        costs = [float(len(path) - 1) for path in path_list]

    min_cost = min(costs)
    # Avoid overflow/underflow in exp
    exps = [math.exp(-(beta) * (cost - min_cost)) for cost in costs]
    total = sum(exps)
    
    if total == 0:
        return path_list[0]

    cumulative = 0.0
    if isinstance(rng, random.Random):
        pick = rng.random() * total
    else:
        pick = random.random() * total
        
    for path, weight in zip(path_list, exps):
        cumulative += weight
        if pick <= cumulative:
            return path
    return path_list[-1]
