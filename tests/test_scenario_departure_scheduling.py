from __future__ import annotations

from smartflow.core.algorithms import histogram_peak
from smartflow.core.floorplan import EdgeSpec, FloorPlan, NodeSpec
from smartflow.core.scenario_loader import create_agents_from_scenario


def _tiny_floorplan() -> FloorPlan:
    nodes = [
        NodeSpec(node_id="A", label="A", kind="room", floor=0, position=(0.0, 0.0, 0.0)),
        NodeSpec(node_id="B", label="B", kind="room", floor=0, position=(10.0, 0.0, 0.0)),
    ]
    edges = [
        EdgeSpec(edge_id="e1", source="A", target="B", length_m=10.0, width_m=2.0, capacity_pps=2.0),
    ]
    return FloorPlan(nodes=nodes, edges=edges)


def test_departure_strategy_minimise_peak_flattens_departures() -> None:
    floorplan = _tiny_floorplan()

    # 100 independent movements all starting at the same period.
    scenario = {
        "random_seed": 1,
        "transition_window_s": 60,
        "behaviour": {
            "departure_strategy": "minimise_peak",
            "departure_bin_s": 5,
        },
        "periods": [
            {
                "id": "P1",
                "start_time": "09:00",
                "movements": [
                    {"origin": "A", "destination": "B", "count": 100}
                ],
            }
        ],
    }

    agents = create_agents_from_scenario(scenario, floorplan, scale=1.0, period_index=-1)
    depart_times = [a.schedule[0].depart_time_s for a in agents]

    # Window 60s / bin 5s => 12 bins.
    # Greedy balancing should keep the peak close to ceil(100/12) == 9.
    peak = histogram_peak(depart_times, bin_size=5.0)
    assert peak <= 10
