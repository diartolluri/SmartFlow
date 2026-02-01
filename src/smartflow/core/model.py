"""Simulation model implementation."""

from __future__ import annotations

import math
import random
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Tuple
import networkx as nx

from .agents import AgentProfile, AgentScheduleEntry
from .dynamics import can_enter_edge, density_speed_factor
from .floorplan import FloorPlan
from .metrics import AgentMetrics, MetricsCollector
from .routing import (
    compute_a_star_path,
    compute_k_shortest_paths,
    compute_path_cost,
    compute_shortest_path,
    choose_route,
)


@dataclass
class SimulationConfig:
    """Runtime configuration for a transition simulation."""

    tick_seconds: float
    transition_window_s: float
    random_seed: int
    k_paths: int = 3
    beta: float = 1.0
    disabled_edges: List[str] = field(default_factory=list)

    # --- Congestion-aware routing (NEA enhancement) ---
    # These defaults are intentionally conservative. Setting alpha=0 disables the feature.
    congestion_alpha: float = 0.0
    congestion_p: float = 2.0
    # Approximate maximum comfortable density (people per m^2) used to derive per-edge capacity.
    congestion_jam_density_ppm2: float = 2.5

    # --- Rerouting stability controls (anti-oscillation) ---
    # Minimum additional spacing between reroutes (on top of per-agent reroute_interval_ticks).
    reroute_cooldown_ticks: int = 0
    # Require a new route to be better by this fractional margin before switching.
    # Example: 0.10 means “at least 10% lower cost”.
    reroute_hysteresis_margin: float = 0.10
    # Only attempt reroute after at least this much waiting has built up.
    reroute_delay_threshold_s: float = 5.0

    # --- Movement realism knobs ---
    # Slow down while traversing stairs (multiplier applied to speed). 1.0 disables.
    stairs_speed_factor: float = 0.7
    # Slow down briefly after sharp turns (applied near the start of an edge).
    # Max slowdown at 180 degrees. Example 0.15 => up to 15% slower.
    turn_slowdown_max: float = 0.15
    # Apply turn slowdown only for the first N meters of the new edge.
    turn_slowdown_distance_m: float = 1.0
    # Add a dwell time when an agent arrives at a toilet node (seconds). 0 disables.
    # Default: 2–5 minutes (uniform).
    toilet_dwell_s: float = 120.0
    # Optional random jitter added to toilet dwell, uniform in [0, toilet_dwell_jitter_s].
    toilet_dwell_jitter_s: float = 180.0

    # --- Lesson changeover + lateness realism ---
    # Nominal time window students have to reach the next lesson.
    lesson_changeover_s: float = 300.0
    # After a student is late, they speed up slightly. This is a small factor per minute late.
    late_speedup_per_min: float = 0.02
    # Cap on the lateness speedup multiplier.
    late_speedup_max: float = 1.15
    # Desired following distance (meters) for headway-based slowdowns.
    following_distance_m: float = 1.0

    # --- Route caching (SQLite) ---
    # If configured, the model will cache deterministic shortest/k-shortest path sets
    # (only when congestion-aware routing is disabled).
    route_cache_enabled: bool = True
    route_cache_db_path: str | None = None
    route_cache_layout_hash: str | None = None

    # --- Algorithm selection ---
    # If True, use A* with a spatial heuristic instead of Dijkstra for shortest paths.
    # A* can be faster on large graphs with good heuristics.
    use_astar: bool = False
    astar_heuristic: str = "auto"  # "auto", "euclidean", "haversine", or "zero"


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
    blocked_until_s: float = 0.0 # Agent cannot start next movement until this time

    # Scheduling / lateness tracking
    scheduled_arrival_s: float | None = None
    actual_arrival_s: float | None = None
    is_late: bool = False


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
        # Latest per-edge congestion ratios (density_ratio). Keyed by (u, v).
        # This is updated once per tick and can be used for debugging, exports, or tests.
        self.congestion_map: Dict[Tuple[str, str], float] = {}
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

            # Respect dwell/wait periods at nodes (e.g., toilets).
            if self.time_s < float(agent.blocked_until_s):
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

                    # Set scheduled arrival for this movement (lesson changeover window).
                    try:
                        changeover = float(self.config.lesson_changeover_s)
                    except Exception:
                        changeover = 300.0
                    agent.scheduled_arrival_s = float(schedule_entry.depart_time_s) + max(0.0, changeover)
                    agent.actual_arrival_s = None
                    
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

    def _is_stairs_edge(self, u: str, v: str, edge_data: dict) -> bool:
        if bool(edge_data.get("is_stairs", False)):
            return True
        # Fallback: any floor change implies stairs/vertical movement.
        try:
            fu = int(self.graph.nodes[u].get("floor", 0))
            fv = int(self.graph.nodes[v].get("floor", 0))
            return fu != fv
        except Exception:
            return False

    def _turn_slowdown_factor(self, agent: AgentRuntimeState) -> float:
        """Return a speed multiplier for the start of an edge after turning."""

        if agent.current_edge is None:
            return 1.0

        max_slow = max(0.0, float(self.config.turn_slowdown_max))
        dist_m = max(0.0, float(self.config.turn_slowdown_distance_m))
        if max_slow <= 0.0 or dist_m <= 0.0:
            return 1.0

        # Only apply near the edge start.
        if agent.position_along_edge > dist_m:
            return 1.0

        u, v = agent.current_edge
        try:
            u_index = agent.route.index(u)
        except ValueError:
            return 1.0
        if u_index <= 0 or u_index + 1 >= len(agent.route):
            return 1.0

        prev_node = agent.route[u_index - 1]
        try:
            p_prev = self.graph.nodes[prev_node].get("position")
            p_u = self.graph.nodes[u].get("position")
            p_v = self.graph.nodes[v].get("position")
            if not (p_prev and p_u and p_v):
                return 1.0

            # Use only X/Y for turn geometry.
            ax, ay = float(p_u[0] - p_prev[0]), float(p_u[1] - p_prev[1])
            bx, by = float(p_v[0] - p_u[0]), float(p_v[1] - p_u[1])
            na = math.hypot(ax, ay)
            nb = math.hypot(bx, by)
            if na <= 1e-9 or nb <= 1e-9:
                return 1.0
            dot = (ax * bx + ay * by) / (na * nb)
            dot = max(-1.0, min(1.0, dot))
            angle = math.acos(dot)  # 0..pi
        except Exception:
            return 1.0

        # Map angle to slowdown linearly: 0 => 1.0, pi => (1 - max_slow)
        factor = 1.0 - max_slow * (angle / math.pi)
        return max(0.1, float(factor))
    def _compute_primary_path(
        self,
        origin: str,
        destination: str,
        stairs_penalty: float,
    ) -> List[str]:
        """Compute primary shortest path using either Dijkstra or A*.
        
        When config.use_astar is True, uses A* with the configured heuristic.
        Otherwise falls back to Dijkstra (compute_shortest_path).
        """
        if self.config.use_astar:
            return list(compute_a_star_path(
                self.graph,
                origin,
                destination,
                stairs_penalty=stairs_penalty,
                heuristic=self.config.astar_heuristic,
                congestion_map=self.congestion_map,
                congestion_alpha=self.config.congestion_alpha,
                congestion_p=self.config.congestion_p,
            ))
        else:
            return list(compute_shortest_path(
                self.graph,
                origin,
                destination,
                stairs_penalty=stairs_penalty,
                congestion_map=self.congestion_map,
                congestion_alpha=self.config.congestion_alpha,
                congestion_p=self.config.congestion_p,
            ))
    def _select_route(self, profile: AgentProfile, movement: AgentScheduleEntry) -> List[str]:
        """Select a route for an agent.

        NEA note (validity):
            - `optimality_beta` controls how strongly agents prefer lower-cost routes.
              Higher beta => more deterministic “shortest path” behaviour.
            - `detour_probability` injects occasional exploration, preventing all agents
              converging on the same corridor in unrealistic lock-step.

        This method supports congestion-aware costs via `self.congestion_map`.
        """

        # Route caching: only safe when congestion-aware routing is disabled.
        can_cache = (
            bool(self.config.route_cache_enabled)
            and bool(self.config.route_cache_db_path)
            and bool(self.config.route_cache_layout_hash)
            and float(self.config.congestion_alpha) <= 0.0
        )

        if can_cache:
            try:
                from smartflow.io import db as dbio

                cached = dbio.get_or_create_cached_route(
                    Path(str(self.config.route_cache_db_path)),
                    layout_hash=str(self.config.route_cache_layout_hash),
                    origin=movement.origin_room,
                    destination=movement.destination_room,
                    stairs_penalty=float(profile.stairs_penalty),
                    key_parts=["shortest"],
                )
                if cached:
                    primary = json.loads(cached)
                else:
                    primary = self._compute_primary_path(
                        movement.origin_room,
                        movement.destination_room,
                        stairs_penalty=profile.stairs_penalty,
                    )
                    dbio.get_or_create_cached_route(
                        Path(str(self.config.route_cache_db_path)),
                        layout_hash=str(self.config.route_cache_layout_hash),
                        origin=movement.origin_room,
                        destination=movement.destination_room,
                        stairs_penalty=float(profile.stairs_penalty),
                        key_parts=["shortest"],
                        path_json=json.dumps(list(primary)),
                        cost=compute_path_cost(
                            self.graph,
                            primary,
                            stairs_penalty=profile.stairs_penalty,
                            congestion_map=self.congestion_map,
                            congestion_alpha=self.config.congestion_alpha,
                            congestion_p=self.config.congestion_p,
                        ),
                    )
            except Exception:
                # Cache must never break routing.
                primary = self._compute_primary_path(
                    movement.origin_room,
                    movement.destination_room,
                    stairs_penalty=profile.stairs_penalty,
                )
        else:
            try:
                primary = self._compute_primary_path(
                    movement.origin_room,
                    movement.destination_room,
                    stairs_penalty=profile.stairs_penalty,
                )
            except nx.NetworkXNoPath:
                raise ValueError(f"No path from {movement.origin_room} to {movement.destination_room}") from None

        # Keep the original error shape for callers.
        if not primary:
            raise ValueError(f"No path from {movement.origin_room} to {movement.destination_room}")
        
        if self.config.k_paths <= 1:
            return list(primary)
            
        if can_cache:
            try:
                from smartflow.io import db as dbio

                cached_k = dbio.get_or_create_cached_route(
                    Path(str(self.config.route_cache_db_path)),
                    layout_hash=str(self.config.route_cache_layout_hash),
                    origin=movement.origin_room,
                    destination=movement.destination_room,
                    stairs_penalty=float(profile.stairs_penalty),
                    key_parts=["kpaths", str(int(self.config.k_paths))],
                )
                if cached_k:
                    paths = json.loads(cached_k)
                else:
                    paths = compute_k_shortest_paths(
                        self.graph,
                        movement.origin_room,
                        movement.destination_room,
                        k=self.config.k_paths,
                        stairs_penalty=profile.stairs_penalty,
                        congestion_map=self.congestion_map,
                        congestion_alpha=self.config.congestion_alpha,
                        congestion_p=self.config.congestion_p,
                    )
                    dbio.get_or_create_cached_route(
                        Path(str(self.config.route_cache_db_path)),
                        layout_hash=str(self.config.route_cache_layout_hash),
                        origin=movement.origin_room,
                        destination=movement.destination_room,
                        stairs_penalty=float(profile.stairs_penalty),
                        key_parts=["kpaths", str(int(self.config.k_paths))],
                        path_json=json.dumps([list(p) for p in paths]),
                        cost=None,
                    )
            except Exception:
                paths = compute_k_shortest_paths(
                    self.graph,
                    movement.origin_room,
                    movement.destination_room,
                    k=self.config.k_paths,
                    stairs_penalty=profile.stairs_penalty,
                    congestion_map=self.congestion_map,
                    congestion_alpha=self.config.congestion_alpha,
                    congestion_p=self.config.congestion_p,
                )
        else:
            paths = compute_k_shortest_paths(
                self.graph,
                movement.origin_room,
                movement.destination_room,
                k=self.config.k_paths,
                stairs_penalty=profile.stairs_penalty,
                congestion_map=self.congestion_map,
                congestion_alpha=self.config.congestion_alpha,
                congestion_p=self.config.congestion_p,
            )
        if not paths:
            return list(primary)
            
        # Pass graph to choose_route for weighted cost calculation.
        # Use per-agent beta (agent heterogeneity) but preserve config.beta as a fallback.
        beta = float(profile.optimality_beta) if getattr(profile, "optimality_beta", None) is not None else float(self.config.beta)
        if self.config.k_paths > 1 and self.rng.random() < float(profile.detour_probability):
            # NEA note: exploration makes behaviour more realistic and reduces oscillation.
            beta = max(0.1, beta * 0.3)

        return list(
            choose_route(
                paths,
                beta,
                graph=self.graph,
                rng=self.rng,
                stairs_penalty=profile.stairs_penalty,
                congestion_map=self.congestion_map,
                congestion_alpha=self.config.congestion_alpha,
                congestion_p=self.config.congestion_p,
            )
        )

    def _edge_capacity_people(self, edge_data: dict) -> float:
        """Estimate a soft capacity (people) for a corridor edge.

        We derive capacity from geometric area and a configurable maximum density.
        This gives a defensible normalisation for 'density_ratio' used in routing costs.
        """

        length_m = float(edge_data.get("length_m", 1.0))
        width_m = float(edge_data.get("width_m", 1.0))
        jam = max(0.1, float(self.config.congestion_jam_density_ppm2))
        # Ensure we never divide by zero.
        area = max(0.1, length_m * max(width_m, 0.1))
        return max(1.0, area * jam)

    def _build_congestion_map(self, occupancy_snapshot: Dict[tuple[str, str], float]) -> Dict[Tuple[str, str], float]:
        """Build a per-tick congestion map.

        Returns:
            Mapping from (u, v) edge keys to density_ratio in [0, +inf).

        NEA note (technique):
            We use a *ratio* rather than raw occupancy so costs remain comparable
            across corridors with different lengths/widths.
        """

        # Count queued agents at the start of an edge (position <= 0). They are not yet
        # inside the corridor but still contribute to perceived congestion.
        queued: Dict[Tuple[str, str], int] = {}
        for agent in self.agents:
            if agent.active and not agent.completed and agent.current_edge is not None:
                if agent.position_along_edge <= 0.0:
                    queued[agent.current_edge] = queued.get(agent.current_edge, 0) + 1

        ratios: Dict[Tuple[str, str], float] = {}
        for u, v, data in self.graph.edges(data=True):
            edge_key = (u, v)
            occ_inside = float(occupancy_snapshot.get(edge_key, 0.0))
            occ_queued = float(queued.get(edge_key, 0))
            # Queue has a weaker effect than 'inside' occupancy (heuristic).
            effective_occ = occ_inside + 0.5 * occ_queued

            cap = self._edge_capacity_people(data)
            ratios[edge_key] = max(0.0, effective_occ / cap)

        return ratios

    def _attempt_reroute(self, agent: AgentRuntimeState, *, current_tick: int) -> bool:
        """Attempt a congestion-aware reroute at a node (anti-oscillation).

        Returns:
            True if the agent's planned route changed.

        NEA note (technique):
            - Cooldown prevents rapid back-and-forth switching.
            - Hysteresis requires a clear improvement before adopting a new route.
            - Rerouting is only attempted at *nodes* (edge start), avoiding unrealistic
              mid-corridor teleports.
        """

        if not agent.current_edge:
            return False

        # Only reroute at the start of the current edge (i.e., agent is at a node).
        if agent.position_along_edge > 0.0:
            return False

        schedule_entry = agent.profile.schedule[agent.schedule_index]
        start_node = agent.current_edge[0]
        target_node = schedule_entry.destination_room
        if start_node == target_node:
            return False

        # Enforce cooldown spacing.
        min_spacing = max(int(agent.profile.reroute_interval_ticks), int(self.config.reroute_cooldown_ticks))
        if min_spacing > 0 and (current_tick - agent.last_reroute_tick) < min_spacing:
            return False

        # Only reroute after meaningful delay (keeps behaviour stable and defensible).
        if agent.waiting_time_s < float(self.config.reroute_delay_threshold_s):
            return False

        # Build the current planned suffix from start_node.
        try:
            start_index = agent.route.index(start_node)
            current_suffix = agent.route[start_index:]
        except ValueError:
            # Defensive fallback: if the planned route is out of sync, treat the
            # current suffix as unknown and allow adopting a sensible candidate.
            start_index = 0
            current_suffix = [start_node]

        # Propose a new route from this node using congestion-weighted costs.
        temp_movement = AgentScheduleEntry(
            period="reroute",
            origin_room=start_node,
            destination_room=target_node,
            depart_time_s=self.time_s,
        )

        try:
            candidate = self._select_route(agent.profile, temp_movement)
        except ValueError:
            return False

        if candidate == current_suffix or len(candidate) < 2:
            return False

        # Hysteresis: accept only if the new route is clearly better.
        # If we do not have a meaningful planned suffix, treat the old cost as
        # effectively infinite so we can recover to a valid route.
        if len(current_suffix) >= 2:
            old_cost = compute_path_cost(
                self.graph,
                current_suffix,
                stairs_penalty=agent.profile.stairs_penalty,
                congestion_map=self.congestion_map,
                congestion_alpha=self.config.congestion_alpha,
                congestion_p=self.config.congestion_p,
            )
        else:
            old_cost = float("inf")
        new_cost = compute_path_cost(
            self.graph,
            candidate,
            stairs_penalty=agent.profile.stairs_penalty,
            congestion_map=self.congestion_map,
            congestion_alpha=self.config.congestion_alpha,
            congestion_p=self.config.congestion_p,
        )

        margin = max(0.0, float(self.config.reroute_hysteresis_margin))
        threshold = old_cost * (1.0 - margin)
        if not (new_cost < threshold):
            return False

        # Commit reroute: replace planned suffix and update current edge.
        if start_index < len(agent.route):
            new_route = agent.route[:start_index] + list(candidate)
        else:
            new_route = list(candidate)
        agent.route = new_route
        agent.path_nodes = list(new_route)
        agent.current_edge = (candidate[0], candidate[1])
        agent.position_along_edge = 0.0
        agent.last_reroute_tick = current_tick
        return True

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

        # Rerouting Logic (congestion-aware + stable)
        current_tick = int(self.time_s / self.config.tick_seconds)
        self._attempt_reroute(agent, current_tick=current_tick)

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

        # Apply stairs slowdown.
        u, v = agent.current_edge
        if self._is_stairs_edge(u, v, edge_data):
            speed *= max(0.1, float(self.config.stairs_speed_factor))

        # Apply turn slowdown near the start of edges.
        speed *= self._turn_slowdown_factor(agent)

        # Apply headway-based slowdown when close behind someone in the same lane.
        if limit_m is not None:
            try:
                desired_gap = max(0.1, float(self.config.following_distance_m))
            except Exception:
                desired_gap = 1.0
            gap = float(limit_m) - float(agent.position_along_edge)
            if gap < desired_gap:
                # Scale speed down smoothly as we approach the leader.
                speed *= max(0.1, max(0.0, gap) / desired_gap)

        # Lateness: after the changeover window, students walk slightly faster.
        if agent.scheduled_arrival_s is not None and self.time_s > float(agent.scheduled_arrival_s):
            minutes_late = (float(self.time_s) - float(agent.scheduled_arrival_s)) / 60.0
            per_min = max(0.0, float(self.config.late_speedup_per_min))
            max_mult = max(1.0, float(self.config.late_speedup_max))
            late_mult = min(max_mult, 1.0 + per_min * minutes_late)
            speed *= late_mult
        
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

            # Record actual arrival and lateness for this movement.
            agent.actual_arrival_s = float(self.time_s)
            if agent.scheduled_arrival_s is not None and agent.actual_arrival_s > float(agent.scheduled_arrival_s):
                agent.is_late = True
            
            agent.active = False
            agent.current_edge = None
            agent.position_along_edge = 0.0
            agent.schedule_index += 1

            # Optional dwell time at toilets.
            try:
                kind = str(node_data.get("kind", "")).lower()
            except Exception:
                kind = ""
            if kind == "toilet":
                base = max(0.0, float(self.config.toilet_dwell_s))
                jitter = max(0.0, float(self.config.toilet_dwell_jitter_s))
                if base > 0.0:
                    extra = self.rng.random() * jitter if jitter > 0.0 else 0.0
                    agent.blocked_until_s = max(float(agent.blocked_until_s), float(self.time_s + base + extra))
            
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

        # Update per-tick congestion map *before* movement so routing decisions
        # can use the current crowding state.
        self.congestion_map = self._build_congestion_map(occupancy_snapshot)

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
                
                # Lane selection policy (stability-focused):
                # - Once an agent is inside a corridor (position > 0), keep their lane.
                # - Only choose/switch lanes at the start of an edge (position <= 0), where it looks natural.
                current_lane = agent.lane_index if agent.lane_index < num_lanes else 0

                if agent.position_along_edge > 0.0:
                    best_lane = current_lane
                    limit_m = lane_limits[best_lane]
                else:
                    # At the edge start, pick the best nearby lane to avoid immediate blockage.
                    candidates = []
                    possible_lanes = {current_lane}
                    if current_lane > 0:
                        possible_lanes.add(current_lane - 1)
                    if current_lane < num_lanes - 1:
                        possible_lanes.add(current_lane + 1)

                    for l in possible_lanes:
                        limit = lane_limits[l]
                        val = float("inf") if limit is None else float(limit)
                        candidates.append((l, val))

                    # Prefer higher limit; slight bias to staying in current lane.
                    candidates.sort(key=lambda x: x[1] + (2.0 if x[0] == current_lane else 0.0), reverse=True)
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
            # Calculate lateness properly:
            # 1. If agent never arrived (actual_arrival_s is None), they're late if simulation ended
            # 2. If agent arrived, compare travel time to changeover window
            is_late = bool(state.is_late)  # Already set during simulation
            
            # Also mark as late if agent didn't complete their journey
            if not state.completed and state.active:
                is_late = True
            
            # Calculate delay as actual time vs expected (changeover window)
            # delay_s should represent how much LONGER than expected the journey took
            if state.scheduled_arrival_s is not None and state.actual_arrival_s is not None:
                # Agent arrived: delay = actual - scheduled (positive = late)
                lateness_s = state.actual_arrival_s - state.scheduled_arrival_s
                delay_s = max(0.0, lateness_s)
            elif state.scheduled_arrival_s is not None and state.actual_arrival_s is None:
                # Agent didn't arrive yet - delay is current time minus deadline
                delay_s = max(0.0, self.time_s - state.scheduled_arrival_s)
            else:
                # Fallback to waiting time
                delay_s = state.waiting_time_s
            
            metrics = AgentMetrics(
                travel_time_s=state.travel_time_s,
                path_nodes=state.path_nodes,
                delay_s=delay_s,
                scheduled_arrival_s=state.scheduled_arrival_s,
                actual_arrival_s=state.actual_arrival_s,
                is_late=is_late,
                role=state.profile.role if hasattr(state.profile, "role") else "student",
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
