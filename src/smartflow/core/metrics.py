"""Metric collectors for SmartFlow runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AgentMetrics:
    travel_time_s: float
    path_nodes: List[str]
    delay_s: float


@dataclass
class EdgeMetrics:
    edge_id: str
    occupancy_over_time: List[float] = field(default_factory=list)


@dataclass
class RunSummary:
    mean_travel_time_s: float | None = None
    p90_travel_time_s: float | None = None
    max_edge_density: float | None = None
    congestion_events: int | None = None


class MetricsCollector:
    """Placeholder aggregator that stores per-agent and per-edge metrics."""

    def __init__(self) -> None:
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.edge_metrics: Dict[str, EdgeMetrics] = {}
        self.summary = RunSummary()

    def record_agent(self, agent_id: str, metrics: AgentMetrics) -> None:
        self.agent_metrics[agent_id] = metrics

    def record_edge_step(self, edge_id: str, occupancy: float) -> None:
        self.edge_metrics.setdefault(edge_id, EdgeMetrics(edge_id)).occupancy_over_time.append(occupancy)

    def finalize(self) -> RunSummary:
        travel_times = [metrics.travel_time_s for metrics in self.agent_metrics.values()]
        if travel_times:
            travel_times_sorted = sorted(travel_times)
            count = len(travel_times_sorted)
            self.summary.mean_travel_time_s = sum(travel_times_sorted) / count
            p90_index = min(int(0.9 * (count - 1)), count - 1)
            self.summary.p90_travel_time_s = travel_times_sorted[p90_index]
        if self.edge_metrics:
            max_density = 0.0
            congestion_events = 0
            for metrics in self.edge_metrics.values():
                if metrics.occupancy_over_time:
                    edge_max = max(metrics.occupancy_over_time)
                    max_density = max(max_density, edge_max)
                    congestion_events += sum(1 for value in metrics.occupancy_over_time if value >= 1.0)
            self.summary.max_edge_density = max_density
            self.summary.congestion_events = congestion_events
        return self.summary
