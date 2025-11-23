"""Utilities for loading scenarios and generating agents."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .agents import AgentProfile, AgentScheduleEntry
from .floorplan import FloorPlan

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
            speed_base_mps=sample(behaviour.get("speed_base_mps"), 1.4),
            stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
            optimality_beta=sample(behaviour.get("optimality_beta"), 1.0),
            reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
            detour_probability=sample(behaviour.get("detour_probability"), 0.0),
            schedule=schedule
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
            speed_base_mps=sample(behaviour.get("speed_base_mps"), 1.4),
            stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
            optimality_beta=sample(behaviour.get("optimality_beta"), 1.0),
            reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
            detour_probability=sample(behaviour.get("detour_probability"), 0.0),
            schedule=[entry]
        )
        agents.append(profile)
        
    return agents
