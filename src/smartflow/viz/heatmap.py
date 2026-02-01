"""Heatmap generation using Matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
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
