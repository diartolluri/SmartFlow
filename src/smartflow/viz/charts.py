"""Chart generation using Matplotlib."""

from __future__ import annotations

from typing import Any, Dict, List

from matplotlib.figure import Figure


def build_travel_time_histogram(agent_metrics: Dict[str, Any]) -> Figure:
    """Generate a histogram of travel times."""
    times = [m.travel_time_s for m in agent_metrics.values()]
    
    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    if times:
        ax.hist(times, bins=20, color='skyblue', edgecolor='black')
        ax.set_xlabel("Travel Time (s)")
        ax.set_ylabel("Count")
        ax.set_title("Distribution of Travel Times")
    else:
        ax.text(0.5, 0.5, "No Data", ha='center', va='center')
        
    fig.tight_layout()
    return fig


def build_active_agents_series(edge_metrics: Dict[str, Any], total_ticks: int, tick_seconds: float = 0.05) -> Figure:
    """Generate a time series of total network occupancy."""
    # Aggregate occupancy across all edges per tick
    total_occupancy = [0.0] * total_ticks
    
    for m in edge_metrics.values():
        series = m.occupancy_over_time
        for i, val in enumerate(series):
            if i < total_ticks:
                total_occupancy[i] += val
                
    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    time_points = [i * tick_seconds for i in range(len(total_occupancy))]
    
    ax.plot(time_points, total_occupancy, color='orange')
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Total Agents Moving")
    ax.set_title("Network Activity Over Time")
    ax.grid(True, linestyle='--', alpha=0.7)
    
    fig.tight_layout()
    return fig


def build_top_edges_bar(
    edges: List[tuple[str, float]],
    *,
    title: str = "Most Congested Edges",
    xlabel: str = "Peak occupancy (people)",
) -> Figure:
    """Build a horizontal bar chart for top congested edges."""

    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot(111)

    if not edges:
        ax.text(0.5, 0.5, "No Data", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    labels = [e[0] for e in edges]
    values = [float(e[1]) for e in edges]

    # Horizontal bars read better with long edge IDs.
    ax.barh(range(len(values)), values, color="#e67e22")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(True, axis="x", linestyle="--", alpha=0.4)

    fig.tight_layout()
    return fig
