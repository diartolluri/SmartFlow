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
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import networkx as nx


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two (lat, lon) points."""

    r = 6_371_000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = phi2 - phi1
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return float(2.0 * r * math.asin(min(1.0, math.sqrt(a))))


def _node_xy(graph: nx.DiGraph, node: str) -> tuple[float, float] | None:
    """Best-effort extraction of an (x, y) coordinate for a node."""

    data: Dict[str, Any] = dict(graph.nodes.get(node, {}))
    for key in ("position", "pos"):
        val = data.get(key)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return (float(val[0]), float(val[1]))
            except Exception:
                pass
    if data.get("x") is not None and data.get("y") is not None:
        try:
            return (float(data.get("x")), float(data.get("y")))
        except Exception:
            return None
    return None


def _node_latlon(graph: nx.DiGraph, node: str) -> tuple[float, float] | None:
    """Best-effort extraction of (lat, lon) for a node."""

    data: Dict[str, Any] = dict(graph.nodes.get(node, {}))
    for lat_key, lon_key in (("lat", "lon"), ("latitude", "longitude")):
        if data.get(lat_key) is not None and data.get(lon_key) is not None:
            try:
                return (float(data.get(lat_key)), float(data.get(lon_key)))
            except Exception:
                return None
    return None


def compute_a_star_path(
    graph: nx.DiGraph,
    source: str,
    target: str,
    *,
    stairs_penalty: float = 0.0,
    congestion_map: Mapping[Tuple[str, str], float] | None = None,
    congestion_alpha: float = 0.0,
    congestion_p: float = 1.0,
    heuristic: str = "auto",
) -> Sequence[str]:
    """Return an A* shortest path between two nodes.

    Heuristic modes:
        - "auto": use Haversine if nodes have lat/lon; else Euclidean on x/y if present; else 0.
        - "haversine": force Haversine (falls back to 0 if lat/lon missing)
        - "euclidean": force Euclidean on x/y (falls back to 0 if x/y missing)
        - "zero": equivalent to Dijkstra
    """

    def w(u: str, v: str, data: dict) -> float:
        ratio = float(congestion_map.get((u, v), 0.0)) if congestion_map is not None else 0.0
        return _edge_weight(
            data,
            stairs_penalty=stairs_penalty,
            density_ratio=ratio,
            congestion_alpha=congestion_alpha,
            congestion_p=congestion_p,
        )

    def h(n1: str, n2: str) -> float:
        mode = str(heuristic or "auto").lower()
        if mode == "zero":
            return 0.0

        if mode in {"auto", "haversine"}:
            a = _node_latlon(graph, n1)
            b = _node_latlon(graph, n2)
            if a is not None and b is not None:
                return _haversine_m(a[0], a[1], b[0], b[1])
            if mode == "haversine":
                return 0.0

        if mode in {"auto", "euclidean"}:
            axy = _node_xy(graph, n1)
            bxy = _node_xy(graph, n2)
            if axy is not None and bxy is not None:
                dx = float(bxy[0] - axy[0])
                dy = float(bxy[1] - axy[1])
                return float((dx * dx + dy * dy) ** 0.5)
            return 0.0

        return 0.0

    return nx.astar_path(graph, source=source, target=target, heuristic=h, weight=w)


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
