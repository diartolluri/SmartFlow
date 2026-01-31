"""Heatmap generation using Matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.figure import Figure


def build_heatmap_figure(
    graph: nx.DiGraph, 
    edge_metrics: Dict[str, Any], 
    title: str = "Congestion Heatmap",
    *,
    floor: int | None = None,
) -> Figure:
    """
    Render a heatmap for edge occupancy across the layout graph.
    
    Returns a Matplotlib Figure object that can be embedded in Tkinter.
    """
    fig = Figure(figsize=(8, 6), dpi=100)
    ax = fig.add_subplot(111)
    
    # Determine which nodes/edges to draw (optionally filter by floor)
    if floor is None:
        node_ids = {n for n in graph.nodes}
    else:
        node_ids = {n for n, data in graph.nodes(data=True) if int(data.get("floor", 0)) == int(floor)}

    # Pre-collect edges so we can guarantee `pos` contains every referenced node.
    edges: List[tuple[str, str]] = []
    colors: List[float] = []
    widths: List[float] = []
    required_nodes: set[str] = set()
    
    for u, v, data in graph.edges(data=True):
        if floor is not None:
            # Only show edges fully on this floor.
            if u not in node_ids or v not in node_ids:
                continue
        edge_id = data.get("id", f"{u}->{v}")
        metric = edge_metrics.get(edge_id)
        
        edges.append((u, v))
        required_nodes.add(str(u))
        required_nodes.add(str(v))
        
        # Default width based on physical width
        w = max(1.0, data.get("width_m", 1.0) * 2)
        widths.append(w)
        
        if metric:
            # Colour by peak occupancy (simple heuristic for now)
            # In future, use density (people/m^2)
            val = metric.peak_occupancy
            colors.append(val)
        else:
            colors.append(0.0)

    # Extract positions with fallbacks.
    # NetworkX drawing requires every node referenced by `edges` to exist in `pos`.
    def _coerce_xy(value: Any) -> tuple[float, float] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return (float(value[0]), float(value[1]))
            except Exception:
                return None
        return None

    pos: Dict[str, tuple[float, float]] = {}
    missing: List[str] = []

    # Prefer drawing all nodes on the selected floor, plus anything required by edges.
    for n in sorted(set(node_ids) | required_nodes):
        data = graph.nodes.get(n, {})
        xy = (
            _coerce_xy(data.get("position"))
            or _coerce_xy(data.get("pos"))
            or (
                (float(data.get("x")), float(data.get("y")))
                if (data.get("x") is not None and data.get("y") is not None)
                else None
            )
        )
        if xy is None:
            missing.append(str(n))
            xy = (0.0, 0.0)
        pos[str(n)] = xy

    # Draw nodes
    nx.draw_networkx_nodes(graph, pos, ax=ax, node_size=50, node_color="lightgray", alpha=0.6)
    
    # Draw edges with colourmap
    if edges:
        # Create a ScalarMappable for the colourbar
        cmap = plt.cm.RdYlGn_r
        norm = plt.Normalize(vmin=min(colors), vmax=max(colors) if max(colors) > 0 else 1.0)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])

        nx.draw_networkx_edges(
            graph, 
            pos, 
            ax=ax, 
            edgelist=edges, 
            edge_color=colors, 
            edge_cmap=cmap,
            edge_vmin=norm.vmin,
            edge_vmax=norm.vmax,
            width=widths,
            arrows=True,
            arrowsize=10
        )
        
        # Add colourbar
        fig.colorbar(sm, ax=ax, label="Peak Occupancy (people)")
    
    ax.set_title(title)
    ax.axis("off")

    # If any nodes were missing positions, show a small note on the plot.
    if missing:
        note = ", ".join(missing[:6]) + ("..." if len(missing) > 6 else "")
        ax.text(0.01, 0.01, f"Missing positions: {note}", transform=ax.transAxes, fontsize=8, alpha=0.7)
    
    return fig


def build_heatmap_image(layout: Any, metrics: Any, output_path: Path | None = None) -> None:
    """Render and save heatmap to file."""
    graph = layout.to_networkx()
    
    # Convert metrics list to dict if needed
    if isinstance(metrics, list):
        metric_map = {m["edge_id"]: m for m in metrics}
    else:
        metric_map = metrics.edge_metrics if hasattr(metrics, "edge_metrics") else metrics

    fig = build_heatmap_figure(graph, metric_map)
    
    if output_path:
        fig.savefig(output_path)
    else:
        plt.show()
