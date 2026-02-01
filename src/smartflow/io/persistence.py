"""High-level helpers for saving and loading simulation runs.

This module exists to keep UI code (Tkinter views) simple and to centralise
how results are translated into a database schema.

NEA note:
    - Separating persistence from UI improves maintainability and testability.
    - The functions here are deterministic given the same inputs.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional
import json

from smartflow.core.metrics import MetricsCollector
from smartflow.io import db


DEFAULT_DB_PATH = Path("smartflow.db")


def save_current_run(
    *,
    floorplan_path: Optional[Path],
    scenario_config: Dict[str, Any],
    results: MetricsCollector,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Persist a run to SQLite and return the new run id.

    Args:
        floorplan_path: Path of the loaded layout JSON. If missing, saving is not possible.
        scenario_config: Dict from the UI config step (duration, seed, scale, beta, data...).
        results: The model's MetricsCollector after `finalize()`.
        db_path: SQLite file location.

    Raises:
        ValueError: If required inputs (like floorplan_path) are missing.
    """

    if floorplan_path is None:
        raise ValueError("Cannot save results: no floorplan_path in app state.")

    db.initialise_database(db_path)

    scenario_id = db.get_or_create_scenario(
        db_path,
        name=floorplan_path.stem,
        layout_hash=db.compute_layout_hash(floorplan_path),
        config=scenario_config,
    )

    summary_obj = results.summary
    summary_dict = asdict(summary_obj)

    # UI config keys are stable: duration/seed/beta (tick_seconds is fixed in RunView).
    summary: Dict[str, Any] = {
        "seed": scenario_config.get("seed"),
        "tick_seconds": 0.05,
        "duration_s": float(scenario_config.get("duration", 0.0)),
        "agent_count": len(results.agent_metrics),
        "mean_travel_time_s": summary_dict.get("mean_travel_time_s"),
        "p50_travel_time_s": summary_dict.get("p50_travel_time_s"),
        "p90_travel_time_s": summary_dict.get("p90_travel_time_s"),
        "p95_travel_time_s": summary_dict.get("p95_travel_time_s"),
        "max_edge_density": summary_dict.get("max_edge_density"),
        "congestion_events": summary_dict.get("congestion_events"),
        "total_throughput": summary_dict.get("total_throughput", 0),
        "time_to_clear_s": summary_dict.get("time_to_clear_s"),
        "percent_late": summary_dict.get("percent_late", 0.0),
    }

    edge_rows = []
    for em in results.edge_metrics.values():
        # Compute a mean occupancy for NEA evidence.
        mean_occ = 0.0
        if em.occupancy_over_time:
            mean_occ = sum(em.occupancy_over_time) / len(em.occupancy_over_time)

        peak_queue = 0
        if em.queue_length_over_time:
            peak_queue = max(em.queue_length_over_time)

        edge_rows.append(
            {
                "edge_id": em.edge_id,
                "peak_occupancy": em.peak_occupancy,
                "peak_duration_ticks": em.peak_duration_ticks,
                "throughput_count": em.throughput_count,
                "mean_occupancy": mean_occ,
                "peak_queue_length": peak_queue,
            }
        )

    agent_rows = []
    for agent_id, am in results.agent_metrics.items():
        # Prefer the metric role if available, else derive from ID
        role = getattr(am, "role", None)
        if not role or role == "unknown":
            role = agent_id.split("_")[0] if "_" in agent_id else "student"
            
        agent_rows.append(
            {
                "agent_id": agent_id,
                "role": role,
                "travel_time_s": float(getattr(am, "travel_time_s", 0.0) or 0.0),
                "delay_s": float(getattr(am, "delay_s", 0.0) or 0.0),
                "scheduled_arrival_s": getattr(am, "scheduled_arrival_s", None),
                "actual_arrival_s": getattr(am, "actual_arrival_s", None),
                "is_late": bool(getattr(am, "is_late", False)),
                "path_json": json.dumps(getattr(am, "path_nodes", []) or []),
            }
        )

    return db.insert_run(db_path, scenario_id, summary, edge_rows, agent_rows)
