"""Agent definitions and behaviour parameterisation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass
class AgentScheduleEntry:
    """Represents a single origin/destination movement request."""

    period: str
    origin_room: str
    destination_room: str
    depart_time_s: float


@dataclass
class AgentProfile:
    """Captures movement behaviour for an individual agent."""

    agent_id: str
    role: str
    speed_base_mps: float
    stairs_penalty: float
    optimality_beta: float
    reroute_interval_ticks: int
    detour_probability: float
    schedule: Sequence[AgentScheduleEntry]

    # Added to support NEA "Detailed Roles" requirement (Diligent, Explorer etc.)
    # without breaking existing constructor if we use default field or post-init.
    # But since we use simple dataclass, we'll modify the constructor calls in scenario_loader.


def _parse_time_to_seconds(value: str) -> float:
    hour, minute = map(int, value.split(":"))
    return float(hour * 3600 + minute * 60)


def _sample_value(spec: dict | float | int | None, rng: random.Random, default: float = 0.0) -> float:
    if spec is None:
        return default
    if isinstance(spec, (int, float)):
        return float(spec)
    if isinstance(spec, dict):
        distribution = spec.get("distribution")
        if "value" in spec:
            return float(spec["value"])
        if "uniform" in spec:
            low, high = spec["uniform"]
            return rng.uniform(float(low), float(high))
        if "lognormal" in spec:
            mean = float(spec["lognormal"].get("mean", 1.0))
            sigma = float(spec["lognormal"].get("sigma", 0.1))
            return rng.lognormvariate(math.log(mean), sigma)
        if distribution == "lognormal":
            mean = float(spec.get("mean", 1.0))
            sigma = float(spec.get("sigma", 0.1))
            return rng.lognormvariate(math.log(mean), sigma)
        if distribution == "uniform":
            low, high = spec.get("low", 0.0), spec.get("high", 1.0)
            return rng.uniform(float(low), float(high))
    raise ValueError(f"Unsupported distribution spec: {spec}")


def generate_agents(seed: int, config: dict) -> List[AgentProfile]:
    """Produce deterministic agent profiles for a simulation run."""

    rng = random.Random(seed)
    behaviour = config.get("behaviour", {})
    speed_spec = behaviour.get("speed_base_mps", {"normal": {"mean": 1.35, "sigma": 0.15}})
    beta_spec = behaviour.get("optimality_beta", {"value": 3.0})
    reroute_spec = behaviour.get("reroute_interval_ticks", {"value": 0})
    detour_spec = behaviour.get("detour_probability", {"value": 0.0})
    stairs_spec = behaviour.get("stairs_penalty", {"student": 3.0})
    jitter_spec = behaviour.get("depart_jitter_s", None)

    agents: List[AgentProfile] = []
    counter = 0

    for period in config.get("periods", []):
        period_id = period["id"]
        start_time = _parse_time_to_seconds(period["start_time"])
        for move in period.get("movements", []):
            population = move.get("population", "student")
            count = int(move.get("count", 0))
            origin = move["origin"]
            destination = move["destination"]
            for i in range(count):
                agent_id = f"{population}_{period_id}_{counter}"
                counter += 1
                depart_time = start_time + _sample_value(jitter_spec, rng, default=0.0)
                schedule_entry = AgentScheduleEntry(
                    period=period_id,
                    origin_room=origin,
                    destination_room=destination,
                    depart_time_s=depart_time,
                )
                if isinstance(stairs_spec, dict):
                    stairs_penalty = float(stairs_spec.get(population, stairs_spec.get("default", 3.0)))
                else:
                    stairs_penalty = float(stairs_spec)
                profile = AgentProfile(
                    agent_id=agent_id,
                    role=population,
                    speed_base_mps=max(0.6, min(2.2, _sample_value(speed_spec, rng, default=1.35))),
                    stairs_penalty=stairs_penalty,
                    optimality_beta=max(0.1, _sample_value(beta_spec, rng, default=3.0)),
                    reroute_interval_ticks=int(round(_sample_value(reroute_spec, rng, default=0.0))),
                    detour_probability=min(1.0, max(0.0, _sample_value(detour_spec, rng, default=0.0))),
                    schedule=[schedule_entry],
                )
                agents.append(profile)
    return agents


def iter_movements(agent: AgentProfile) -> Iterable[AgentScheduleEntry]:
    """Iterate through the agent's planned movements."""

    return iter(agent.schedule)
