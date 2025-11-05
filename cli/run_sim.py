"""Command-line entry point for headless SmartFlow runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SmartFlow simulation headlessly")
    parser.add_argument("layout", type=Path, help="Path to floor plan JSON")
    parser.add_argument("scenario", type=Path, help="Path to scenario configuration JSON")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory to write outputs (agent_metrics.csv, edge_metrics.csv, summary.json)",
        default=Path("outputs"),
    )
    return parser.parse_args()


def main() -> None:
    """Parse arguments and dispatch to the simulation pipeline."""

    import sys
    from importlib import import_module

    project_root = Path(__file__).resolve().parents[1]
    sys.path.append(str(project_root))

    generate_agents = import_module("smartflow.core.agents").generate_agents
    load_floorplan = import_module("smartflow.core.floorplan").load_floorplan
    model_module = import_module("smartflow.core.model")
    SimulationConfig = model_module.SimulationConfig
    SmartFlowModel = model_module.SmartFlowModel
    export_csv = import_module("smartflow.io.exporters").export_csv
    load_scenario = import_module("smartflow.io.importers").load_scenario

    args = parse_args()
    floorplan = load_floorplan(args.layout)
    scenario = load_scenario(args.scenario)

    agents = generate_agents(int(scenario.get("random_seed", 0)), scenario)
    config = SimulationConfig(
        tick_seconds=float(scenario["tick_seconds"]),
        transition_window_s=float(scenario["transition_window_s"]),
        random_seed=int(scenario["random_seed"]),
        k_paths=int(scenario.get("routing", {}).get("k_paths", 3)),
    )

    model = SmartFlowModel(floorplan=floorplan, agents=agents, config=config)
    collector = model.run()

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    agent_rows = [
        {
            "agent_id": agent_id,
            "travel_time_s": metrics.travel_time_s,
            "delay_s": metrics.delay_s,
            "path_nodes": "->".join(metrics.path_nodes),
        }
        for agent_id, metrics in collector.agent_metrics.items()
    ]
    export_csv(output_dir / "agent_metrics.csv", agent_rows)

    edge_rows = [
        {
            "edge_id": edge_id,
            "tick_index": idx,
            "occupancy": value,
        }
        for edge_id, metrics in collector.edge_metrics.items()
        for idx, value in enumerate(metrics.occupancy_over_time)
    ]
    export_csv(output_dir / "edge_metrics.csv", edge_rows)

    summary = collector.summary
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "mean_travel_time_s": summary.mean_travel_time_s,
                "p90_travel_time_s": summary.p90_travel_time_s,
                "max_edge_density": summary.max_edge_density,
                "congestion_events": summary.congestion_events,
                "agents": len(collector.agent_metrics),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Completed simulation with {len(agent_rows)} agents. Results saved to {output_dir}")


if __name__ == "__main__":
    main()
