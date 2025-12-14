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
    beta: float = 1.0
    disabled_edges: List[str] = field(default_factory=list)


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
    schedule_index: int = 0
    last_reroute_tick: int = 0
    lane_index: int = 0 # For multi-lane logic and visualisation
    lateral_offset: float = 0.0 # Visual offset (-1.0 to 1.0) for rendering lanes


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
        self.config = config
        
        # Apply edge disablements
        if config.disabled_edges:
            # Find edges by ID and remove them
            edges_to_remove = []
            for u, v, data in self.graph.edges(data=True):
                if data.get("id") in config.disabled_edges:
                    edges_to_remove.append((u, v))
            self.graph.remove_edges_from(edges_to_remove)

        self.agents: List[AgentRuntimeState] = [AgentRuntimeState(profile=a) for a in agents]
        self.collector = MetricsCollector()
        self.rng = rng or random.Random(config.random_seed)
        self.edge_occupancy: Dict[tuple[str, str], float] = {}
        self.node_occupancy: Dict[str, int] = {} # Track people in nodes
        self.time_s = 0.0
        
        # Initialise node occupancy from starting positions
        for agent in self.agents:
            if agent.profile.schedule:
                start_node = agent.profile.schedule[0].origin_room
                self.node_occupancy[start_node] = self.node_occupancy.get(start_node, 0) + 1

    def _activate_agents(self) -> None:
        for agent in self.agents:
            if agent.active or agent.completed:
                continue
            
            if agent.schedule_index >= len(agent.profile.schedule):
                agent.completed = True
                continue

            schedule_entry = agent.profile.schedule[agent.schedule_index]
            if schedule_entry.depart_time_s <= self.time_s:
                try:
                    agent.route = self._select_route(agent.profile, schedule_entry)
                    agent.active = True
                    agent.path_nodes = list(agent.route)
                    
                    # Agent leaves the origin node
                    origin = schedule_entry.origin_room
                    if self.node_occupancy.get(origin, 0) > 0:
                        self.node_occupancy[origin] -= 1
                        
                    if len(agent.route) < 2:
                        # Already at destination or invalid path
                        agent.active = False
                        agent.schedule_index += 1
                        # Re-enter destination node immediately
                        dest = schedule_entry.destination_room
                        self.node_occupancy[dest] = self.node_occupancy.get(dest, 0) + 1
                    else:
                        agent.current_edge = (agent.route[0], agent.route[1])
                        agent.position_along_edge = 0.0
                except ValueError:
                    # Pathfinding failed, skip this movement
                    agent.schedule_index += 1

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
            
        # Pass graph to choose_route for weighted cost calculation
        # Use config.beta for the choice model
        return list(choose_route(paths, self.config.beta, graph=self.graph, rng=self.rng))

    def _attempt_reroute(self, agent: AgentRuntimeState) -> None:
        """Try to find a better path from current location to destination."""
        if not agent.current_edge:
            return
            
        current_node = agent.current_edge[0] # Reroute from start of current edge? Or end?
        # If we are in the middle of an edge, we must finish it. So reroute from target.
        start_node = agent.current_edge[1]
        
        schedule_entry = agent.profile.schedule[agent.schedule_index]
        target_node = schedule_entry.destination_room
        
        if start_node == target_node:
            return

        # Create a temporary movement entry for routing
        temp_movement = AgentScheduleEntry(
            period="reroute",
            origin_room=start_node,
            destination_room=target_node,
            depart_time_s=self.time_s
        )
        
        try:
            new_suffix = self._select_route(agent.profile, temp_movement)
            # new_suffix starts with start_node. 
            # agent.route currently has [... , u, v, ...]. agent.current_edge is (u, v).
            # We want to replace everything after v with new_suffix[1:]
            
            # Find index of v in current route
            try:
                v_index = agent.route.index(start_node)
                # Keep path up to v
                new_route = agent.route[:v_index+1] + new_suffix[1:]
                agent.route = new_route
                # Update path nodes for metrics
                agent.path_nodes = list(new_route) # Note: this overwrites history in metrics? 
                # Actually metrics usually track the *actual* path taken. 
                # But here path_nodes is just the planned route. 
                # For true tracking we'd need a separate history list.
            except ValueError:
                pass
        except ValueError:
            pass # Reroute failed, stick to current plan

    def _advance_agent(
        self,
        agent: AgentRuntimeState,
        occupancy_snapshot: Dict[tuple[str, str], float],
        next_occupancy: Dict[tuple[str, str], float],
        queue_counts: Dict[tuple[str, str], int],
        newly_entered: Dict[tuple[str, str], int],
        limit_m: float | None = None,
    ) -> None:
        if agent.current_edge is None or not agent.active:
            return
            
        # Rerouting Logic
        current_tick = int(self.time_s / self.config.tick_seconds)
        if (agent.profile.reroute_interval_ticks > 0 and 
            current_tick - agent.last_reroute_tick >= agent.profile.reroute_interval_ticks):
            
            agent.last_reroute_tick = current_tick
            # Only reroute if experiencing significant delay
            if agent.waiting_time_s > 5.0: 
                 self._attempt_reroute(agent)

        edge_data = self.graph.get_edge_data(*agent.current_edge)
        length_m = edge_data.get("length_m", 1.0)
        width_m = edge_data.get("width_m", 1.0)
        
        occupancy = occupancy_snapshot.get(agent.current_edge, 0.0)
        entered_this_tick = newly_entered.get(agent.current_edge, 0)
        
        # Check entry condition if at start of edge
        if agent.position_along_edge <= 0.0:
            if not can_enter_edge(occupancy + entered_this_tick, length_m, width_m):
                agent.waiting_time_s += self.config.tick_seconds
                queue_counts[agent.current_edge] = queue_counts.get(agent.current_edge, 0) + 1
                return
            else:
                # Successfully entering
                newly_entered[agent.current_edge] = entered_this_tick + 1
                self.collector.record_edge_entry(f"{agent.current_edge[0]}->{agent.current_edge[1]}")

        speed_base = agent.profile.speed_base_mps
        # Use total occupancy for speed calculation too, to reflect immediate congestion
        density_factor = density_speed_factor(occupancy + entered_this_tick, length_m, width_m)
        speed = max(0.1, speed_base * density_factor)
        
        proposed_pos = agent.position_along_edge + speed * self.config.tick_seconds
        
        # Apply collision avoidance limit
        if limit_m is not None:
            # If limit is beyond the edge, we clamp to the limit but allow exiting if limit >= length
            # Actually, if limit_m < length_m, we are blocked on this edge.
            # If limit_m >= length_m, we are effectively not blocked on this edge.
            if proposed_pos > limit_m:
                proposed_pos = limit_m
                # If we are blocked, we might be waiting
                agent.waiting_time_s += self.config.tick_seconds * 0.5 # Partial wait?
        
        agent.position_along_edge = proposed_pos
        
        if agent.position_along_edge < length_m:
            next_occupancy[agent.current_edge] = next_occupancy.get(agent.current_edge, 0.0) + 1.0
            return
            
        remaining = agent.position_along_edge - length_m
        
        # Check if we can find the current node in the route
        try:
            current_index = agent.route.index(agent.current_edge[1])
        except ValueError:
            # Should not happen if route is consistent
            agent.active = False
            return

        # Node Capacity Check (Phase 4)
        target_node_id = agent.current_edge[1]
        node_data = self.graph.nodes[target_node_id]
        capacity = node_data.get("capacity", 1000)
        current_node_occ = self.node_occupancy.get(target_node_id, 0)
        
        if current_node_occ >= capacity:
            # Node is full! Block entry.
            agent.position_along_edge = length_m # Stay at end of edge
            agent.waiting_time_s += self.config.tick_seconds
            next_occupancy[agent.current_edge] = next_occupancy.get(agent.current_edge, 0.0) + 1.0
            # Record queueing?
            queue_counts[agent.current_edge] = queue_counts.get(agent.current_edge, 0) + 1
            return

        if current_index == len(agent.route) - 1:
            # Reached destination for this movement
            # Enter the node permanently (until next schedule)
            self.node_occupancy[target_node_id] = current_node_occ + 1
            
            agent.active = False
            agent.current_edge = None
            agent.position_along_edge = 0.0
            agent.schedule_index += 1
            
            # Check if fully completed
            if agent.schedule_index >= len(agent.profile.schedule):
                agent.completed = True
        else:
            # Passing through node
            # Momentarily check capacity (already done above)
            # If we pass, we don't increment node_occupancy permanently because we enter next edge immediately
            # BUT, strictly speaking, we are "in" the node for 0 time?
            # If we want to model "Node Congestion", we should increment it?
            # But then we need to decrement it when entering next edge.
            # Since we enter next edge in THIS tick, the net change is 0.
            # So we just proceed.
            
            next_node = agent.route[current_index + 1]
            agent.current_edge = (agent.current_edge[1], next_node)
            agent.position_along_edge = max(0.0, remaining)
            if agent.position_along_edge > 0.0:
                next_occupancy[agent.current_edge] = next_occupancy.get(agent.current_edge, 0.0) + 1.0

    def step(self) -> None:
        self._activate_agents()
        occupancy_snapshot = self._compute_edge_occupancy()
        next_occupancy: Dict[tuple[str, str], float] = {}
        queue_counts: Dict[tuple[str, str], int] = {}
        
        # Track agents that successfully enter an edge during this tick
        # to prevent overcrowding from simultaneous entries
        newly_entered: Dict[tuple[str, str], int] = {}
        
        # Group agents by edge to enforce ordering
        agents_by_edge: Dict[tuple[str, str], List[AgentRuntimeState]] = {}
        for agent in self.agents:
            if agent.active and not agent.completed and agent.current_edge:
                agents_by_edge.setdefault(agent.current_edge, []).append(agent)
        
        # Process each edge
        for edge, edge_agents in agents_by_edge.items():
            # Sort by position descending (furthest ahead first)
            edge_agents.sort(key=lambda a: a.position_along_edge, reverse=True)
            
            # Multi-lane logic
            # Determine number of lanes based on edge width
            edge_data = self.graph.get_edge_data(*edge)
            width_m = edge_data.get("width_m", 2.0)
            # Assume 0.6m per lane/person width
            num_lanes = max(1, int(width_m / 0.6))
            
            # Track the limit (furthest back tail) for each lane
            # Initialise with None (meaning no limit/end of edge)
            lane_limits = [None] * num_lanes
            
            for agent in edge_agents:
                agent.travel_time_s += self.config.tick_seconds
                original_edge = agent.current_edge
                
                # Find the best lane (the one that allows moving furthest)
                # If multiple lanes allow full movement (limit is None), pick random or keep current?
                # To minimise lane switching flickering, prefer current lane if it's good.
                
                best_lane = 0
                max_limit = -1.0
                
                # Check current lane first
                current_lane = agent.lane_index if agent.lane_index < num_lanes else 0
                
                # Simple greedy assignment:
                # Pick the lane with the largest limit (furthest ahead obstruction)
                
                # We need to handle "None" which means "Infinity" (unblocked)
                # Let's treat None as float('inf')
                
                best_lane = -1
                best_val = -1.0
                
                # Try to stick to current lane if possible to avoid jitter
                # But if blocked, switch.
                
                candidates = []
                # Restrict to adjacent lanes only (current, left, right)
                # This prevents "pinging" across the corridor
                possible_lanes = {current_lane}
                if current_lane > 0: possible_lanes.add(current_lane - 1)
                if current_lane < num_lanes - 1: possible_lanes.add(current_lane + 1)
                
                for l in possible_lanes:
                    limit = lane_limits[l]
                    val = float('inf') if limit is None else limit
                    candidates.append((l, val))
                
                # Sort candidates: prefer higher limit. If equal, prefer current lane.
                # We add a significant bias (2.0m) to current lane to prevent rapid switching (jitter)
                candidates.sort(key=lambda x: x[1] + (2.0 if x[0] == current_lane else 0), reverse=True)
                
                best_lane = candidates[0][0]
                limit_m = lane_limits[best_lane]
                
                # Assign agent to this lane
                agent.lane_index = best_lane
                
                # Calculate lateral offset for visualisation
                # Map lane index 0..N-1 to -0.5..0.5 range (normalised width)
                if num_lanes > 1:
                    # Center the lanes
                    # e.g. 2 lanes: -0.25, +0.25
                    # e.g. 3 lanes: -0.33, 0, +0.33
                    agent.lateral_offset = ((best_lane + 0.5) / num_lanes) - 0.5
                else:
                    agent.lateral_offset = 0.0
                
                self._advance_agent(
                    agent, 
                    occupancy_snapshot, 
                    next_occupancy, 
                    queue_counts, 
                    newly_entered,
                    limit_m=limit_m
                )
                
                # Update limit for this lane
                if agent.current_edge != original_edge:
                    # Agent left the edge
                    # The lane is now open up to the end (or rather, the agent is gone from this edge)
                    # So we don't update the limit for this lane (it remains what it was, or becomes None?)
                    # Actually, if the agent leaves, they don't block THIS edge anymore.
                    # So the limit remains whatever it was before this agent (which is effectively "None" relative to agents behind? No.)
                    # Wait, if agent leaves, they are NOT on the edge.
                    # So they shouldn't affect lane_limits for subsequent agents on this edge.
                    pass
                else:
                    # Agent is still on the edge. Next agent in this lane must stop before this one.
                    # Use a small gap (e.g. 0.5m)
                    lane_limits[best_lane] = max(0.0, agent.position_along_edge - 0.5)
        
        self.edge_occupancy = next_occupancy
        
        # Record metrics for ALL edges to ensure time-series alignment
        # This is slightly more expensive but ensures charts work correctly
        for u, v, data in self.graph.edges(data=True):
            occ = next_occupancy.get((u, v), 0.0)
            q = queue_counts.get((u, v), 0)
            
            edge_id = data.get("id", f"{u}->{v}")
            self.collector.record_edge_step(edge_id, occ, queue_length=q)
            
        self.time_s += self.config.tick_seconds

    @property
    def is_complete(self) -> bool:
        """Check if all agents have finished their schedules."""
        return all(agent.completed for agent in self.agents)

    def run(self) -> MetricsCollector:
        total_ticks = int(self.config.transition_window_s / self.config.tick_seconds)
        for _ in range(total_ticks):
            self.step()
            if self.is_complete:
                break
                
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
