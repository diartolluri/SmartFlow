"""Tests for congestion-aware rerouting (Task A).

These tests focus on deterministic properties:
- Congestion cost is monotonic.
- Rerouting only occurs at nodes (edge start), not mid-edge.
- With high congestion, a better route is adopted when hysteresis allows.
"""

from __future__ import annotations

import networkx as nx

from smartflow.core.routing import compute_path_cost
from smartflow.core.floorplan import EdgeSpec, FloorPlan, NodeSpec
from smartflow.core.agents import AgentProfile, AgentScheduleEntry
from smartflow.core.model import SimulationConfig, SmartFlowModel


def test_congestion_cost_is_monotonic() -> None:
    g = nx.DiGraph()
    g.add_edge("A", "B", length_m=10.0, width_m=2.0, is_stairs=False)

    base = compute_path_cost(g, ["A", "B"], congestion_alpha=2.0, congestion_p=2.0)
    higher = compute_path_cost(
        g,
        ["A", "B"],
        congestion_map={("A", "B"): 1.0},
        congestion_alpha=2.0,
        congestion_p=2.0,
    )
    assert higher > base


def _simple_plan() -> FloorPlan:
    nodes = [
        NodeSpec(node_id="A", label="A", kind="room", floor=0, position=(0.0, 0.0, 0.0)),
        NodeSpec(node_id="B", label="B", kind="junction", floor=0, position=(1.0, 0.0, 0.0)),
        NodeSpec(node_id="C", label="C", kind="room", floor=0, position=(2.0, 0.0, 0.0)),
        NodeSpec(node_id="D", label="D", kind="junction", floor=0, position=(1.0, 1.0, 0.0)),
    ]
    edges = [
        EdgeSpec(edge_id="AB", source="A", target="B", length_m=1.0, width_m=2.0, capacity_pps=2.0),
        EdgeSpec(edge_id="BC", source="B", target="C", length_m=1.0, width_m=2.0, capacity_pps=2.0),
        EdgeSpec(edge_id="AD", source="A", target="D", length_m=1.0, width_m=2.0, capacity_pps=2.0),
        EdgeSpec(edge_id="DC", source="D", target="C", length_m=1.0, width_m=2.0, capacity_pps=2.0),
    ]
    return FloorPlan(nodes=nodes, edges=edges)


def test_reroute_does_not_happen_mid_edge() -> None:
    plan = _simple_plan()
    entry = AgentScheduleEntry(period="p", origin_room="A", destination_room="C", depart_time_s=0.0)
    profile = AgentProfile(
        agent_id="a1",
        role="student",
        speed_base_mps=1.4,
        stairs_penalty=0.0,
        optimality_beta=10_000.0,
        reroute_interval_ticks=0,
        detour_probability=0.0,
        schedule=[entry],
    )

    config = SimulationConfig(
        tick_seconds=0.1,
        transition_window_s=10.0,
        random_seed=1,
        congestion_alpha=5.0,
        reroute_hysteresis_margin=0.0,
        reroute_delay_threshold_s=0.0,
    )

    model = SmartFlowModel(plan, [profile], config)
    state = model.agents[0]
    state.active = True
    state.route = ["A", "B", "C"]
    state.current_edge = ("A", "B")
    state.position_along_edge = 0.5  # mid-edge
    state.waiting_time_s = 999.0

    # Even though congestion would favour a different route, mid-edge reroute must not occur.
    model.congestion_map = {("A", "B"): 10.0, ("B", "C"): 10.0}
    changed = model._attempt_reroute(state, current_tick=100)
    assert changed is False
    assert state.route == ["A", "B", "C"]


def test_reroute_switches_to_better_route_at_node() -> None:
    plan = _simple_plan()
    entry = AgentScheduleEntry(period="p", origin_room="A", destination_room="C", depart_time_s=0.0)
    profile = AgentProfile(
        agent_id="a1",
        role="student",
        speed_base_mps=1.4,
        stairs_penalty=0.0,
        optimality_beta=10_000.0,
        reroute_interval_ticks=0,
        detour_probability=0.0,
        schedule=[entry],
    )

    config = SimulationConfig(
        tick_seconds=0.1,
        transition_window_s=10.0,
        random_seed=1,
        congestion_alpha=10.0,
        congestion_p=2.0,
        reroute_hysteresis_margin=0.0,
        reroute_delay_threshold_s=0.0,
    )

    model = SmartFlowModel(plan, [profile], config)
    state = model.agents[0]
    state.active = True
    state.route = ["A", "B", "C"]
    state.current_edge = ("A", "B")
    state.position_along_edge = 0.0  # at node
    state.waiting_time_s = 999.0

    # Make A->B->C extremely congested so A->D->C becomes preferred.
    model.congestion_map = {("A", "B"): 5.0, ("B", "C"): 5.0, ("A", "D"): 0.0, ("D", "C"): 0.0}

    changed = model._attempt_reroute(state, current_tick=1)
    assert changed is True
    assert state.route[:3] == ["A", "D", "C"]
