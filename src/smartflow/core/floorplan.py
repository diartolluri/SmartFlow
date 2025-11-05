"""Floor plan loading and validation utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import networkx as nx


@dataclass(frozen=True)
class NodeSpec:
    """Describes a room, junction, or stair node within the school layout."""

    node_id: str
    label: str
    kind: str
    floor: int
    position: Tuple[float, float, float]
    metadata: Dict[str, float] | None = None


@dataclass(frozen=True)
class EdgeSpec:
    """Describes a directed edge with capacity and geometry metadata."""

    edge_id: str
    source: str
    target: str
    length_m: float
    width_m: float
    capacity_pps: float
    is_stairs: bool = False
    metadata: Dict[str, float] | None = None


@dataclass
class FloorPlan:
    """Container for node and edge specifications."""

    nodes: List[NodeSpec]
    edges: List[EdgeSpec]

    def node_ids(self) -> Iterable[str]:
        return (node.node_id for node in self.nodes)

    def edge_ids(self) -> Iterable[str]:
        return (edge.edge_id for edge in self.edges)

    def to_networkx(self) -> nx.DiGraph:
        """Convert the plan into a directed graph with edge attributes."""

        graph = nx.DiGraph()
        for node in self.nodes:
            graph.add_node(
                node.node_id,
                label=node.label,
                kind=node.kind,
                floor=node.floor,
                position=node.position,
                metadata=node.metadata or {},
            )
        for edge in self.edges:
            graph.add_edge(
                edge.source,
                edge.target,
                id=edge.edge_id,
                length_m=edge.length_m,
                width_m=edge.width_m,
                capacity_pps=edge.capacity_pps,
                is_stairs=edge.is_stairs,
                metadata=edge.metadata or {},
            )
        return graph


def load_floorplan(path: Path) -> FloorPlan:
    """Load a floor plan JSON file and return a parsed FloorPlan model."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = [
        NodeSpec(
            node_id=item["id"],
            label=item.get("label", item["id"]),
            kind=item.get("type", "junction"),
            floor=int(item.get("floor", 0)),
            position=tuple(float(x) for x in item.get("pos", [0.0, 0.0, 0.0])),
            metadata={k: v for k, v in item.items() if k not in {"id", "label", "type", "floor", "pos"}},
        )
        for item in data.get("nodes", [])
    ]
    edges = [
        EdgeSpec(
            edge_id=item.get("id") or f"edge_{idx}",
            source=item["from"],
            target=item["to"],
            length_m=float(item.get("length_m", 1.0)),
            width_m=float(item.get("width_m", 1.0)),
            capacity_pps=float(item.get("capacity_pps", 1.0)),
            is_stairs=bool(item.get("is_stairs", False)),
            metadata={k: v for k, v in item.items() if k not in {"id", "from", "to", "length_m", "width_m", "capacity_pps", "is_stairs"}},
        )
        for idx, item in enumerate(data.get("edges", []))
    ]
    plan = FloorPlan(nodes=nodes, edges=edges)
    validate_floorplan(plan)
    return plan


def validate_floorplan(plan: FloorPlan) -> None:
    """Validate the integrity of a floor plan."""

    node_ids = {node.node_id for node in plan.nodes}
    if not node_ids:
        raise ValueError("Floor plan must contain at least one node")
    if len(node_ids) != len(plan.nodes):
        raise ValueError("Duplicate node IDs detected in floor plan")

    edge_ids = set()
    for edge in plan.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError(f"Edge {edge.edge_id} references unknown nodes")
        if edge.edge_id in edge_ids:
            raise ValueError(f"Duplicate edge ID detected: {edge.edge_id}")
        edge_ids.add(edge.edge_id)
        if edge.length_m <= 0 or edge.width_m <= 0:
            raise ValueError(f"Edge {edge.edge_id} must have positive length and width")
        if edge.capacity_pps <= 0:
            raise ValueError(f"Edge {edge.edge_id} must have positive capacity")

    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)
    graph.add_edges_from((edge.source, edge.target) for edge in plan.edges)
    if not nx.is_weakly_connected(graph):
        raise ValueError("Floor plan graph must be weakly connected")
