"""Routing and path choice utilities."""

from __future__ import annotations

import math
import random
from typing import Iterable, List, Sequence

import networkx as nx


def _edge_weight(data: dict, stairs_penalty: float = 0.0) -> float:
    base = data.get("length_m", 1.0) / max(data.get("width_m", 1.0), 0.1)
    if data.get("is_stairs", False):
        base += stairs_penalty
    return float(base)


def compute_shortest_path(graph: nx.DiGraph, source: str, target: str, *, stairs_penalty: float = 0.0) -> Sequence[str]:
    """Return the shortest path between two nodes in the layout graph."""

    return nx.shortest_path(
        graph,
        source=source,
        target=target,
        weight=lambda u, v, data: _edge_weight(data, stairs_penalty=stairs_penalty),
    )


def compute_k_shortest_paths(
    graph: nx.DiGraph,
    source: str,
    target: str,
    *,
    k: int = 3,
    stairs_penalty: float = 0.0,
) -> List[Sequence[str]]:
    """Return a collection of the *k* best routes for diversification."""

    generator = nx.shortest_simple_paths(
        graph,
        source,
        target,
        weight=lambda u, v, data: _edge_weight(data, stairs_penalty=stairs_penalty),
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
    rng: random.Random | None = None
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
            cost = 0.0
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                data = graph.get_edge_data(u, v)
                # Use the same weight function as shortest path
                cost += _edge_weight(data)
            costs.append(cost)
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
