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
    title: str = "Congestion Heatmap"
) -> Figure:
    """
    Render a heatmap for edge occupancy across the layout graph.
    
    Returns a Matplotlib Figure object that can be embedded in Tkinter.
    """
    fig = Figure(figsize=(8, 6), dpi=100)
    ax = fig.add_subplot(111)
    
    # Extract positions
    pos = {n: data["position"][:2] for n, data in graph.nodes(data=True)}
    
    # Determine edge colours based on peak occupancy or density
    edges = []
    colors = []
    widths = []
    
    for u, v, data in graph.edges(data=True):
        edge_id = data.get("id", f"{u}->{v}")
        metric = edge_metrics.get(edge_id)
        
        edges.append((u, v))
        
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

    # Draw nodes
    nx.draw_networkx_nodes(
        graph, pos, ax=ax, node_size=50, node_color="lightgray", alpha=0.6
    )
    
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
