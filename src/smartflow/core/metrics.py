"""Metric collectors for SmartFlow runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .algorithms import mergesort


@dataclass
class AgentMetrics:
    travel_time_s: float
    path_nodes: List[str]
    delay_s: float
    scheduled_arrival_s: float | None = None
    actual_arrival_s: float | None = None
    is_late: bool = False
    role: str = "unknown" # e.g. student:diligent


@dataclass
class EdgeMetrics:
    edge_id: str
    occupancy_over_time: List[float] = field(default_factory=list)
    throughput_count: int = 0
    queue_length_over_time: List[int] = field(default_factory=list)
    peak_occupancy: float = 0.0
    peak_duration_ticks: int = 0


@dataclass
class RunSummary:
    mean_travel_time_s: float | None = None
    p50_travel_time_s: float | None = None
    p90_travel_time_s: float | None = None
    p95_travel_time_s: float | None = None
    max_edge_density: float | None = None
    congestion_events: int | None = None
    total_throughput: int = 0
    time_to_clear_s: float | None = None
    percent_late: float = 0.0


class MetricsCollector:
    """Aggregator that stores per-agent and per-edge metrics."""

    def __init__(self) -> None:
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.edge_metrics: Dict[str, EdgeMetrics] = {}
        self.summary = RunSummary()

    def record_agent(self, agent_id: str, metrics: AgentMetrics) -> None:
        self.agent_metrics[agent_id] = metrics

    def record_edge_step(self, edge_id: str, occupancy: float, queue_length: int = 0) -> None:
        metrics = self.edge_metrics.setdefault(edge_id, EdgeMetrics(edge_id))
        metrics.occupancy_over_time.append(occupancy)
        metrics.queue_length_over_time.append(queue_length)
        if occupancy > metrics.peak_occupancy:
            metrics.peak_occupancy = occupancy
        # Count ticks where occupancy suggests congestion (e.g. > 1 person roughly)
        # Note: This is a simple heuristic; density-based analysis happens in post-processing
        if occupancy >= 1.0:
            metrics.peak_duration_ticks += 1

    def record_edge_entry(self, edge_id: str) -> None:
        self.edge_metrics.setdefault(edge_id, EdgeMetrics(edge_id)).throughput_count += 1

    def finalize(self) -> RunSummary:
        travel_times = [metrics.travel_time_s for metrics in self.agent_metrics.values()]
        if travel_times:
            # NEA evidence: use mergesort (stable, O(n log n)) instead of built-in sort.
            travel_times_sorted = mergesort(travel_times)
            count = len(travel_times_sorted)
            self.summary.mean_travel_time_s = sum(travel_times_sorted) / count
            
            def get_percentile(p: float) -> float:
                idx = min(int(p * (count - 1)), count - 1)
                return travel_times_sorted[idx]
                
            self.summary.p50_travel_time_s = get_percentile(0.5)
            self.summary.p90_travel_time_s = get_percentile(0.9)
            self.summary.p95_travel_time_s = get_percentile(0.95)
            self.summary.time_to_clear_s = max(travel_times)
            
            # Calculate lateness percentage
            late_count = sum(1 for m in self.agent_metrics.values() if m.is_late)
            self.summary.percent_late = (late_count / count) * 100.0

        if self.edge_metrics:
            max_density = 0.0
            congestion_events = 0
            total_throughput = 0
            for metrics in self.edge_metrics.values():
                total_throughput += metrics.throughput_count
                if metrics.occupancy_over_time:
                    edge_max = max(metrics.occupancy_over_time)
                    max_density = max(max_density, edge_max)
                    # Define congestion event as queue formation
                    congestion_events += sum(1 for q in metrics.queue_length_over_time if q > 0)
            
            self.summary.max_edge_density = max_density
            self.summary.congestion_events = congestion_events
            self.summary.total_throughput = total_throughput
            
        return self.summary
