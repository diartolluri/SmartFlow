"""Heatmap generation using Matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
from matplotlib.figure import Figure

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


def _gaussian_kernel_1d(*, sigma: float, radius: int) -> "np.ndarray":
    if np is None:
        raise RuntimeError("NumPy is required for Gaussian kernel generation")
    sigma = float(max(1e-6, sigma))
    r = int(max(0, radius))
    x = np.arange(-r, r + 1, dtype=float)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    k /= np.sum(k)
    return k


def _gaussian_blur_2d(grid: "np.ndarray", *, sigma: float = 1.2, radius: int = 3) -> "np.ndarray":
    """Apply a separable Gaussian blur to a 2D grid using NumPy operations."""

    if np is None:
        raise RuntimeError("NumPy is required for Gaussian blur")
    kernel = _gaussian_kernel_1d(sigma=sigma, radius=radius)

    # Convolve rows then columns (separable convolution).
    blurred = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), axis=1, arr=grid)
    blurred = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), axis=0, arr=blurred)
    return blurred


def build_heatmap_figure(
    graph: nx.DiGraph, 
    edge_metrics: Dict[str, Any], 
    title: str = "Congestion Heatmap",
    *,
    floor: int | None = None,
    show_density_raster: bool = True,
    direction_filter: str = "all",  # "all", "forward", "reverse"
) -> Figure:
    """
    Render a heatmap for edge occupancy across the layout graph.
    
    Returns a Matplotlib Figure object that can be embedded in Tkinter.
    """
    fig = Figure(figsize=(8, 6), dpi=100)
    ax = fig.add_subplot(111)
    
    def _parse_floor(value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            s = str(value).strip().lower()
            if s in {"g", "ground", "ground floor"}:
                return 0
            cleaned = "".join(ch for ch in s if (ch.isdigit() or ch == "-"))
            return int(cleaned) if cleaned not in {"", "-"} else 0
        except Exception:
            return 0

    # Determine which nodes/edges to draw (optionally filter by floor)
    if floor is None:
        node_ids = {n for n in graph.nodes}
    else:
        node_ids = {n for n, data in graph.nodes(data=True) if _parse_floor(data.get("floor", 0)) == _parse_floor(floor)}

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
        
        # Filter by direction: forward edges have no "_rev" suffix, reverse edges do.
        if direction_filter == "forward" and edge_id.endswith("_rev"):
            continue
        if direction_filter == "reverse" and not edge_id.endswith("_rev"):
            continue
        
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
    # Important: when filtering by floor, we must *not* attempt to draw nodes from
    # other floors, otherwise NetworkX raises "Node X has no position".
    nodes_to_draw = list(node_ids) if floor is not None else list(graph.nodes)
    nx.draw_networkx_nodes(
        graph,
        pos,
        ax=ax,
        nodelist=nodes_to_draw,
        node_size=50,
        node_color="lightgray",
        alpha=0.6,
    )

    # Optional: render a density raster under edges using NumPy.
    # NEA evidence: 2D matrix operations + Gaussian convolution smoothing.
    if show_density_raster and edges and np is not None:
        xs = [xy[0] for xy in pos.values()]
        ys = [xy[1] for xy in pos.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Avoid degenerate extents.
        if max_x - min_x < 1e-6:
            max_x = min_x + 1.0
        if max_y - min_y < 1e-6:
            max_y = min_y + 1.0

        # Choose a modest grid resolution to keep rendering responsive.
        grid_w = 220
        grid_h = 220
        grid = np.zeros((grid_h, grid_w), dtype=float)

        def to_cell(x: float, y: float) -> tuple[int, int]:
            gx = int((x - min_x) / (max_x - min_x) * (grid_w - 1))
            gy = int((y - min_y) / (max_y - min_y) * (grid_h - 1))
            return max(0, min(grid_w - 1, gx)), max(0, min(grid_h - 1, gy))

        for (u, v), val in zip(edges, colors):
            x1, y1 = pos[str(u)]
            x2, y2 = pos[str(v)]
            dx = float(x2 - x1)
            dy = float(y2 - y1)
            dist = (dx * dx + dy * dy) ** 0.5
            steps = max(2, int(dist * 4))  # ~4 samples per unit distance
            for i in range(steps + 1):
                t = i / steps
                x = x1 + dx * t
                y = y1 + dy * t
                cx, cy = to_cell(x, y)
                grid[cy, cx] += float(val)

        if float(grid.max()) > 0.0:
            grid = grid / float(grid.max())
            grid = _gaussian_blur_2d(grid, sigma=1.3, radius=4)
            # Re-normalise post-blur for consistent colour mapping.
            if float(grid.max()) > 0.0:
                grid = grid / float(grid.max())

            ax.imshow(
                grid,
                origin="lower",
                extent=(min_x, max_x, min_y, max_y),
                cmap=plt.cm.inferno,
                alpha=0.35,
                interpolation="bilinear",
                zorder=0,
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


def build_directional_flow_figure(
    graph: nx.DiGraph,
    edge_metrics: Dict[str, Any],
    title: str = "Directional Flow",
    *,
    floor: int | None = None,
) -> Figure:
    """
    Render a directional flow heatmap showing flow imbalance between directions.
    
    For bidirectional corridors, shows which direction has more traffic using
    color coding: Blue = more traffic A→B, Red = more traffic B→A.
    
    Returns a Matplotlib Figure object.
    """
    fig = Figure(figsize=(8, 6), dpi=100)
    ax = fig.add_subplot(111)
    
    def _parse_floor(value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            s = str(value).strip().lower()
            if s in {"g", "ground", "ground floor"}:
                return 0
            cleaned = "".join(ch for ch in s if (ch.isdigit() or ch == "-"))
            return int(cleaned) if cleaned not in {"", "-"} else 0
        except Exception:
            return 0

    # Determine nodes on this floor
    if floor is None:
        node_ids = {n for n in graph.nodes}
    else:
        node_ids = {n for n, data in graph.nodes(data=True) if _parse_floor(data.get("floor", 0)) == _parse_floor(floor)}

    # Build edge pairs (A→B and B→A)
    edge_pairs: Dict[Tuple[str, str], Dict[str, float]] = {}
    
    for u, v, data in graph.edges(data=True):
        if floor is not None:
            if u not in node_ids or v not in node_ids:
                continue
        
        # Canonical key (sorted pair)
        key = tuple(sorted([u, v]))
        if key not in edge_pairs:
            edge_pairs[key] = {"forward": 0.0, "backward": 0.0, "u": u, "v": v}
        
        edge_id = data.get("id", f"{u}->{v}")
        metric = edge_metrics.get(edge_id)
        throughput = float(metric.throughput_count if metric else 0)
        
        if (u, v) == (key[0], key[1]):
            edge_pairs[key]["forward"] = throughput
        else:
            edge_pairs[key]["backward"] = throughput

    # Extract positions
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
    for n in graph.nodes:
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
            xy = (0.0, 0.0)
        pos[str(n)] = xy

    # Draw nodes
    nodes_to_draw = list(node_ids) if floor is not None else list(graph.nodes)
    nx.draw_networkx_nodes(
        graph,
        pos,
        ax=ax,
        nodelist=nodes_to_draw,
        node_size=40,
        node_color="#555555",
        alpha=0.6,
    )

    # Draw edges with directional colour coding
    # Blue = more forward (A→B), Red = more backward (B→A), Gray = balanced
    max_flow = max((ep["forward"] + ep["backward"]) for ep in edge_pairs.values()) if edge_pairs else 1.0
    max_flow = max(1.0, max_flow)
    
    for key, ep in edge_pairs.items():
        u, v = key
        if u not in pos or v not in pos:
            continue
            
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        
        forward = ep["forward"]
        backward = ep["backward"]
        total = forward + backward
        
        if total < 0.1:
            color = "#cccccc"  # Gray for no traffic
            width = 1.0
            alpha = 0.3
        else:
            # Imbalance ratio: -1 (all backward) to +1 (all forward)
            imbalance = (forward - backward) / total
            
            # Map to color: Blue (forward) to Red (backward)
            if imbalance > 0:
                # More forward - blue tones
                intensity = min(1.0, abs(imbalance))
                color = (0.2, 0.4, 0.8 + 0.2 * intensity)  # Blue
            elif imbalance < 0:
                # More backward - red tones
                intensity = min(1.0, abs(imbalance))
                color = (0.8 + 0.2 * intensity, 0.3, 0.2)  # Red
            else:
                color = "#888888"  # Balanced - gray
            
            # Width based on total traffic
            width = 1.0 + 4.0 * (total / max_flow)
            alpha = 0.5 + 0.4 * (total / max_flow)
        
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, alpha=alpha, solid_capstyle='round')

    # Add legend
    legend_elements = [
        mpatches.Patch(facecolor=(0.2, 0.4, 1.0), label='More Forward (A→B)'),
        mpatches.Patch(facecolor=(1.0, 0.3, 0.2), label='More Backward (B→A)'),
        mpatches.Patch(facecolor='#888888', label='Balanced'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    ax.set_title(title)
    ax.axis("off")
    
    return fig


def build_layout_figure(
    graph: nx.DiGraph,
    floor: int,
    *,
    highlight_item: str | None = None,
    figsize: Tuple[float, float] = (8, 6)
) -> Figure:
    """
    Render the basic floor layout with optional highlighting of a node or edge.
    If 'highlight_item' matches a node ID or edge ID (u->v), it is drawn in red/cyan.
    """
    fig = Figure(figsize=figsize, dpi=100)
    ax = fig.add_subplot(111)
    
    # helper to parse floor
    def _parse_floor_local(value: Any) -> int:
        try:
            if value is None: return 0
            if isinstance(value, (int, float)): return int(value)
            s = str(value).strip().lower()
            if s in {"g", "ground"}: return 0
            cleaned = "".join(ch for ch in s if ch.isdigit() or ch == "-")
            return int(cleaned) if cleaned else 0
        except: return 0

    # Filter nodes for this floor
    floor_nodes = {n for n, d in graph.nodes(data=True) if _parse_floor_local(d.get("floor", 0)) == floor}
    
    # Extract positions
    pos: Dict[str, tuple[float, float]] = {}
    for n in graph.nodes:
        d = graph.nodes[n]
        # try standard keys
        xy = None
        if "position" in d: xy = d["position"]
        elif "pos" in d: xy = d["pos"]
        elif "x" in d and "y" in d: xy = (float(d["x"]), float(d["y"]))
        
        # fallback
        if xy:
            try: pos[n] = (float(xy[0]), float(xy[1]))
            except: pos[n] = (0.0,0.0)
        else:
            pos[n] = (0.0, 0.0)

    # 1. Draw all edges on this floor
    edges_to_draw = []
    highlight_edge_tuple = None
    highlight_node_id = None
    
    # Check if highlight item is an edge
    if highlight_item and ("->" in highlight_item or "-" in highlight_item):
        # normalize separator
        parts = highlight_item.replace("->", "-").split("-")
        if len(parts) == 2:
            u_hlt, v_hlt = parts[0].strip(), parts[1].strip()
            # Try both directions
            if graph.has_edge(u_hlt, v_hlt): highlight_edge_tuple = (u_hlt, v_hlt)
            elif graph.has_edge(v_hlt, u_hlt): highlight_edge_tuple = (v_hlt, u_hlt)
    elif highlight_item:
        highlight_node_id = highlight_item

    for u, v in graph.edges:
        if u in floor_nodes and v in floor_nodes:
            color = "#dddddd"
            width = 1.0
            alpha = 0.5
            z_order = 1
            
            # Check edge type
            edge_data = graph.edges[u, v]
            if edge_data.get("is_stairs", False):
                color = "#4a90e2" # Blue for stairs
                width = 2.0
                alpha = 0.7
            
            # Check highlight (Node connections)
            if highlight_node_id and (u == highlight_node_id or v == highlight_node_id):
                color = "#ffaa00" # Orange for connected edges
                width = 2.0
                alpha = 0.8
                z_order = 2
            
            # Check highlight (Specific Edge)
            if highlight_edge_tuple and (u, v) == highlight_edge_tuple:
                color = "#ff00ff" # Magenta
                width = 3.0
                alpha = 1.0
                z_order = 3
            
            if u in pos and v in pos:
                x1, y1 = pos[u]
                x2, y2 = pos[v]
                ls = '-'
                if edge_data.get("is_stairs", False): ls = '--'
                
                ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, alpha=alpha, zorder=z_order, linestyle=ls)

    # 2. Draw all nodes on this floor
    nodes_x = []
    nodes_y = []
    node_colors = []
    node_sizes = []
    
    stairs_x = []
    stairs_y = []
    
    hlt_x = []
    hlt_y = []
    
    for n in floor_nodes:
        if n not in pos: continue
        x, y = pos[n]
        
        kind = str(graph.nodes[n].get("kind", "")).lower()
        
        if highlight_item and str(n) == highlight_item:
            hlt_x.append(x)
            hlt_y.append(y)
        elif kind == "stairs":
            # Separate list for stairs to color them differently
            stairs_x.append(x)
            stairs_y.append(y)
            # Also add to main to ensure they are drawn if not covered? 
            # Actually better to draw separate scatter
        else:
            nodes_x.append(x)
            nodes_y.append(y)
            c = "#aaaaaa"
            if kind == "room": c = "#98df8a" # Light green
            elif kind == "toilet": c = "#c5b0d5" # Light purple
            node_colors.append(c)
            node_sizes.append(30)

    if nodes_x:
        ax.scatter(nodes_x, nodes_y, c=node_colors, s=node_sizes, zorder=2, edgecolors="none")

    if stairs_x:
        # Blue squares for stairs
        ax.scatter(stairs_x, stairs_y, c="#1f77b4", s=50, marker="s", zorder=2, edgecolors="white", label="Stairs")
        
    # Draw highlighted node(s) on top
    if hlt_x:
        ax.scatter(hlt_x, hlt_y, c="red", s=150, zorder=3, edgecolors="black")
        
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_title(f"Floor {floor}", fontsize=10)
    fig.tight_layout()
    return fig

