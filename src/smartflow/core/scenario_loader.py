"""Utilities for loading scenarios and generating agents."""

from __future__ import annotations

import heapq
import random
from typing import Any, Dict, List, Optional

from .agents import AgentProfile, AgentScheduleEntry
from .floorplan import FloorPlan


def _schedule_departures_minimise_peak(
    *,
    count: int,
    start_time_s: float,
    window_s: float,
    bin_s: float,
    rng: random.Random,
) -> List[float]:
    """Assign departure times to minimise the peak number of departures per bin.

    This is a greedy minimisation algorithm:
      - Split the window into equal-sized bins (bin_s)
      - Repeatedly place the next departure into the bin with the lowest current load

    Implementation detail:
        Uses a min-heap so selecting the least-loaded bin is O(log B).
        Overall complexity is O(N log B).

    Returns:
        List of departure times (seconds), length == count.
    """

    n = max(0, int(count))
    if n == 0:
        return []

    window_s = float(max(1.0, window_s))
    bin_s = float(max(1.0, bin_s))
    bins = max(1, int(window_s // bin_s))

    heap: list[tuple[int, int]] = [(0, i) for i in range(bins)]
    heapq.heapify(heap)

    times: List[float] = []
    for _ in range(n):
        load, idx = heapq.heappop(heap)
        load += 1
        heapq.heappush(heap, (load, idx))

        # Place inside the chosen bin with a uniform offset to avoid identical depart times.
        t = float(start_time_s) + (idx + rng.random()) * bin_s
        t = min(float(start_time_s) + window_s, max(float(start_time_s), t))
        times.append(t)

    return times

def create_agents_from_scenario(
    scenario_data: Dict[str, Any], 
    floorplan: FloorPlan,
    scale: float = 1.0, 
    period_index: int = -1
) -> List[AgentProfile]:
    """
    Generate a list of AgentProfiles based on the scenario definition.
    
    Args:
        scenario_data: The full scenario configuration.
        floorplan: The floorplan object (for validation).
        scale: Population scaling factor.
        period_index: If >= 0, only generate agents for this specific period index.
    """
    agents = []
    seed = scenario_data.get("random_seed", 42)
    rng = random.Random(seed)
    
    behaviour = scenario_data.get("behaviour", {})

    # Sensible defaults (m/s): typical walking speed ~1.3–1.4 m/s with individual variation.
    # If scenario doesn't define a speed distribution, use a small normal spread.
    behaviour.setdefault("speed_base_mps", {"normal": {"mean": 1.35, "sigma": 0.15}})

    # Agent-based heterogeneity for route choice: each agent gets its own optimality.
    # Higher beta => more deterministic “shortest path” behaviour.
    behaviour.setdefault("optimality_beta", {"normal": {"mean": 1.0, "sigma": 0.5}})

    # Departure staggering strategy (NEA: scheduling/minimisation).
    # - "minimise_peak": spreads departures evenly across a changeover window.
    # - "random": legacy behaviour (depart_jitter only).
    behaviour.setdefault("departure_strategy", "minimise_peak")
    behaviour.setdefault("departure_bin_s", 5)

    toilet_nodes = {n.node_id for n in floorplan.nodes if n.kind == "toilet"}
    room_nodes = [n.node_id for n in floorplan.nodes if n.kind == "room"]

    def is_toilet(node_id: str) -> bool:
        return node_id in toilet_nodes

    def pick_room_destination() -> Optional[str]:
        if not room_nodes:
            return None
        return rng.choice(room_nodes)

    def ensure_toilet_leads_to_room(schedule: List[AgentScheduleEntry]) -> List[AgentScheduleEntry]:
        """If a schedule ever sends an agent to a toilet, ensure they subsequently go to a room.

        If the scenario already includes toilet->room, we leave it unchanged.
        If the toilet movement is terminal (or breaks the chain), we insert a toilet->room leg.
        """

        if not schedule:
            return schedule

        updated: List[AgentScheduleEntry] = []
        for idx, entry in enumerate(schedule):
            updated.append(entry)

            if not is_toilet(entry.destination_room):
                continue

            # If next leg already departs from this toilet and ends at a room, do nothing.
            next_entry = schedule[idx + 1] if idx + 1 < len(schedule) else None
            if next_entry is not None:
                if next_entry.origin_room == entry.destination_room and (next_entry.destination_room in room_nodes):
                    continue

            # Otherwise, insert toilet -> room.
            dest_room = pick_room_destination()
            if dest_room is None:
                continue

            updated.append(
                AgentScheduleEntry(
                    period=entry.period,
                    origin_room=entry.destination_room,
                    destination_room=dest_room,
                    # Depart time can be "now"; model will still wait out toilet dwell.
                    depart_time_s=float(entry.depart_time_s),
                )
            )

        return updated
    
    # Helper for sampling distributions
    def sample(spec: Any, default: float = 0.0) -> float:
        if spec is None: return default
        if isinstance(spec, (int, float)): return float(spec)
        if isinstance(spec, dict):
            if "value" in spec: return float(spec["value"])
            if "uniform" in spec: 
                # Expecting {"uniform": [low, high]}
                return rng.uniform(spec["uniform"][0], spec["uniform"][1])
            if "lognormal" in spec: 
                # Expecting {"lognormal": {"mean": ..., "sigma": ...}}
                params = spec["lognormal"]
                return rng.lognormvariate(params.get("mean", 0.0), params.get("sigma", 1.0))
            if "normal" in spec: 
                # Expecting {"normal": {"mean": ..., "sigma": ...}}
                params = spec["normal"]
                return rng.normalvariate(params.get("mean", 0.0), params.get("sigma", 1.0))
        return default

    agent_id_counter = 0
    
    # Helper to parse time
    def parse_time(t_str: str) -> float:
        try:
            h, m = map(int, t_str.split(":"))
            return h * 3600.0 + m * 60.0
        except:
            return 0.0

    # Find earliest start time to normalize
    start_times = []
    all_periods = scenario_data.get("periods", [])
    
    # Filter periods if index specified
    target_periods = []
    if period_index >= 0:
        if period_index < len(all_periods):
            target_periods = [all_periods[period_index]]
        else:
            return [] # Invalid index
    else:
        target_periods = all_periods

    for p in all_periods:
        if "start_time" in p:
            start_times.append(parse_time(p["start_time"]))
    
    min_time = min(start_times) if start_times else 0.0

    # Changeover window used for departure staggering.
    # Prefer explicit scenario config, otherwise fall back to the GUI default (5 minutes).
    window_s = float(
        scenario_data.get("transition_window_s")
        or scenario_data.get("transition_window")
        or behaviour.get("transition_window_s")
        or 300.0
    )
    bin_s = float(behaviour.get("departure_bin_s") or 5.0)

    # 1. Group movements
    movements_by_chain: Dict[str, List[Dict]] = {}
    standalone_movements: List[Dict] = []
    
    for period in target_periods:
        period_id = period["id"]
        period_start = period.get("start_time", "00:00")
        
        for move in period.get("movements", []):
            count = int(move.get("count", 1) * scale)
            chain_id = move.get("chain_id")
            
            if chain_id:
                if chain_id not in movements_by_chain:
                    movements_by_chain[chain_id] = []
                movements_by_chain[chain_id].append({
                    **move, 
                    "period_id": period_id,
                    "period_start_time": period_start
                })
            else:
                for _ in range(count):
                    standalone_movements.append({
                        **move, 
                        "period_id": period_id,
                        "period_start_time": period_start
                    })

    # Optional scheduling/minimisation: pre-assign departure times for standalone movements.
    # We schedule *within each period* so we flatten the peak departures during lesson changeover.
    departure_strategy = str(behaviour.get("departure_strategy") or "random").strip().lower()
    scheduled_departures_by_period: Dict[str, List[float]] = {}
    if standalone_movements and departure_strategy == "minimise_peak":
        period_counts: Dict[str, int] = {}
        period_start_rel: Dict[str, float] = {}
        for move in standalone_movements:
            pid = str(move["period_id"])
            period_counts[pid] = period_counts.get(pid, 0) + 1
            ps = parse_time(move.get("period_start_time", "00:00"))
            period_start_rel[pid] = float(ps - (ps if period_index >= 0 else min_time))

        for pid, cnt in period_counts.items():
            start_rel = float(period_start_rel.get(pid, 0.0))
            scheduled_departures_by_period[pid] = _schedule_departures_minimise_peak(
                count=cnt,
                start_time_s=start_rel,
                window_s=window_s,
                bin_s=bin_s,
                rng=rng,
            )

    # 2. Create Agents from Chains
    for chain_id, moves in movements_by_chain.items():
        agent_id_counter += 1
        
        schedule = []
        first_move = moves[0]
        
        if period_index >= 0:
            ref_time = parse_time(first_move.get("period_start_time", "00:00"))
        else:
            ref_time = min_time

        chain_start_time = parse_time(first_move.get("period_start_time", "00:00")) - ref_time
        
        jitter = sample(behaviour.get("depart_jitter_s"), 0.0)
        current_time = chain_start_time + max(0.0, jitter)
        
        valid_chain = True
        for move in moves:
            origin = move["origin"]
            dest = move["destination"]
            delay = move.get("delay_s", 0.0)
            current_time += delay
            
            if origin not in list(floorplan.node_ids()) or dest not in list(floorplan.node_ids()):
                valid_chain = False
                break

            entry = AgentScheduleEntry(
                period=move["period_id"],
                origin_room=origin,
                destination_room=dest,
                depart_time_s=current_time
            )
            schedule.append(entry)
        
        if not valid_chain or not schedule:
            continue
        
        profile = AgentProfile(
            agent_id=f"student_chain_{chain_id}",
            role="student",
            speed_base_mps=max(0.6, min(2.2, sample(behaviour.get("speed_base_mps"), 1.35))),
            stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
            optimality_beta=max(0.1, min(10.0, sample(behaviour.get("optimality_beta"), 1.0))),
            reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
            detour_probability=sample(behaviour.get("detour_probability"), 0.0),
            schedule=ensure_toilet_leads_to_room(schedule)
        )
        agents.append(profile)

    # 3. Create Agents from Standalone
    for move in standalone_movements:
        agent_id_counter += 1
        origin = move["origin"]
        dest = move["destination"]
        
        if origin not in list(floorplan.node_ids()) or dest not in list(floorplan.node_ids()):
            continue
        
        period_start_s = parse_time(move.get("period_start_time", "00:00"))
        
        if period_index >= 0:
            ref_time = period_start_s
        else:
            ref_time = min_time

        relative_start = period_start_s - ref_time
        
        if departure_strategy == "minimise_peak":
            pool = scheduled_departures_by_period.get(str(move["period_id"]), [])
            depart_time = float(pool.pop() if pool else relative_start)
        else:
            jitter = sample(behaviour.get("depart_jitter_s"), 0.0)
            depart_time = relative_start + max(0.0, jitter)
        
        entry = AgentScheduleEntry(
            period=move["period_id"],
            origin_room=origin,
            destination_room=dest,
            depart_time_s=depart_time
        )
        
        profile = AgentProfile(
            agent_id=f"student_{agent_id_counter}",
            role="student",
            speed_base_mps=max(0.6, min(2.2, sample(behaviour.get("speed_base_mps"), 1.35))),
            stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
            optimality_beta=max(0.1, min(10.0, sample(behaviour.get("optimality_beta"), 1.0))),
            reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
            detour_probability=sample(behaviour.get("detour_probability"), 0.0),
            schedule=ensure_toilet_leads_to_room([entry])
        )
        agents.append(profile)
        
    return agents
