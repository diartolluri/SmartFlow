"""Simulation model implementation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List
import networkx as nx

from .agents import AgentProfile, AgentScheduleEntry
from .dynamics import can_enter_edge, density_speed_factor
from .floorplan import FloorPlan
from .metrics import AgentMetrics, MetricsCollector
from .routing import compute_k_shortest_paths, compute_shortest_path, choose_route


@dataclass
class SimulationConfig:
    """Runtime configuration for a transition simulation."""

    tick_seconds: float
    transition_window_s: float
    random_seed: int
    k_paths: int = 3


@dataclass
class AgentRuntimeState:
    profile: AgentProfile
    route: List[str] = field(default_factory=list)
    current_edge: tuple[str, str] | None = None
    position_along_edge: float = 0.0
    active: bool = False
    completed: bool = False
    travel_time_s: float = 0.0
    waiting_time_s: float = 0.0
    path_nodes: List[str] = field(default_factory=list)


class SmartFlowModel:
    """Simulation engine for corridor movement."""

    def __init__(
        self,
        floorplan: FloorPlan,
        agents: Iterable[AgentProfile],
        config: SimulationConfig,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.floorplan = floorplan
        self.graph: nx.DiGraph = floorplan.to_networkx()
        self.agents: List[AgentRuntimeState] = [AgentRuntimeState(profile=a) for a in agents]
        self.config = config
        self.collector = MetricsCollector()
        self.rng = rng or random.Random(config.random_seed)
        self.edge_occupancy: Dict[tuple[str, str], float] = {}
        self.time_s = 0.0

    def _activate_agents(self) -> None:
        for agent in self.agents:
            if agent.active or agent.completed:
                continue
            schedule_entry = agent.profile.schedule[0]
            if schedule_entry.depart_time_s <= self.time_s:
                agent.active = True
                agent.route = self._select_route(agent.profile, schedule_entry)
                agent.path_nodes = list(agent.route)
                if len(agent.route) < 2:
                    agent.completed = True
                else:
                    agent.current_edge = (agent.route[0], agent.route[1])
                    agent.position_along_edge = 0.0

    def _select_route(self, profile: AgentProfile, movement: AgentScheduleEntry) -> List[str]:
        try:
            primary = compute_shortest_path(
                self.graph,
                movement.origin_room,
                movement.destination_room,
                stairs_penalty=profile.stairs_penalty,
            )
        except nx.NetworkXNoPath:
            raise ValueError(f"No path from {movement.origin_room} to {movement.destination_room}") from None
        if self.config.k_paths <= 1:
            return list(primary)
        paths = compute_k_shortest_paths(
            self.graph,
            movement.origin_room,
            movement.destination_room,
            k=self.config.k_paths,
            stairs_penalty=profile.stairs_penalty,
        )
        if not paths:
            return list(primary)
        return list(choose_route(paths, profile.optimality_beta, rng=self.rng))

    def _advance_agent(
        self,
        agent: AgentRuntimeState,
        occupancy_snapshot: Dict[tuple[str, str], float],
        next_occupancy: Dict[tuple[str, str], float],
    ) -> None:
        if agent.current_edge is None or agent.completed:
            return
        edge_data = self.graph.get_edge_data(*agent.current_edge)
        capacity = edge_data.get("capacity_pps", 1.0)
        occupancy = occupancy_snapshot.get(agent.current_edge, 0.0)
        if agent.position_along_edge <= 0.0 and not can_enter_edge(occupancy, capacity):
            agent.waiting_time_s += self.config.tick_seconds
            return
        speed_base = agent.profile.speed_base_mps
        density_factor = density_speed_factor(occupancy, capacity)
        distance = edge_data.get("length_m", 1.0)
        speed = max(0.1, speed_base * density_factor)
        agent.position_along_edge += speed * self.config.tick_seconds
        if agent.position_along_edge < distance:
            next_occupancy[agent.current_edge] = next_occupancy.get(agent.current_edge, 0.0) + 1.0
            return
        remaining = agent.position_along_edge - distance
        current_index = agent.route.index(agent.current_edge[1])
        if current_index == len(agent.route) - 1:
            agent.completed = True
            agent.active = False
            agent.current_edge = None
            agent.position_along_edge = 0.0
        else:
            next_node = agent.route[current_index + 1]
            agent.current_edge = (agent.current_edge[1], next_node)
            agent.position_along_edge = max(0.0, remaining)
            if agent.position_along_edge > 0.0:
                next_occupancy[agent.current_edge] = next_occupancy.get(agent.current_edge, 0.0) + 1.0

    def step(self) -> None:
        self._activate_agents()
        occupancy_snapshot = self._compute_edge_occupancy()
        next_occupancy: Dict[tuple[str, str], float] = {}
        for agent in self.agents:
            if agent.active and not agent.completed:
                agent.travel_time_s += self.config.tick_seconds
                self._advance_agent(agent, occupancy_snapshot, next_occupancy)
        self.edge_occupancy = next_occupancy
        for (u, v), occ in next_occupancy.items():
            self.collector.record_edge_step(f"{u}->{v}", occ)
        self.time_s += self.config.tick_seconds

    def run(self) -> MetricsCollector:
        total_ticks = int(self.config.transition_window_s / self.config.tick_seconds)
        for _ in range(total_ticks):
            self.step()
        for state in self.agents:
            metrics = AgentMetrics(
                travel_time_s=state.travel_time_s,
                path_nodes=state.path_nodes,
                delay_s=state.waiting_time_s,
            )
            self.collector.record_agent(state.profile.agent_id, metrics)
        self.collector.finalize()
        return self.collector

    def _compute_edge_occupancy(self) -> Dict[tuple[str, str], float]:
        occupancy: Dict[tuple[str, str], float] = {}
        for agent in self.agents:
            if agent.active and not agent.completed and agent.current_edge is not None:
                if agent.position_along_edge > 0.0:
                    occupancy[agent.current_edge] = occupancy.get(agent.current_edge, 0.0) + 1.0
        return occupancy
