"""Tests for SQLite persistence (Task B).

These tests verify that a run can be saved to a fresh database and read back.
"""

from __future__ import annotations

import json
from pathlib import Path

from smartflow.core.metrics import AgentMetrics, MetricsCollector
from smartflow.io.persistence import save_current_run
from smartflow.io.db import (
    get_dashboard_stats,
    get_or_create_cached_route,
    get_run_agent_aggregates,
    get_run_summary,
    get_top_edges_for_run,
    initialise_database,
)


def test_save_and_load_run(tmp_path: Path) -> None:
    # Minimal floorplan file for hashing.
    layout = {
        "nodes": [
            {"id": "A", "label": "A", "type": "room", "floor": 0, "pos": [0, 0, 0]},
            {"id": "B", "label": "B", "type": "room", "floor": 0, "pos": [1, 0, 0]},
        ],
        "edges": [
            {"id": "AB", "from": "A", "to": "B", "length_m": 1.0, "width_m": 2.0, "capacity_pps": 2.0},
        ],
    }
    floorplan_path = tmp_path / "layout.json"
    floorplan_path.write_text(json.dumps(layout), encoding="utf-8")

    collector = MetricsCollector()
    collector.record_agent("a1", AgentMetrics(travel_time_s=12.0, path_nodes=["A", "B"], delay_s=3.0))
    collector.record_agent("a2", AgentMetrics(travel_time_s=10.0, path_nodes=["A", "B"], delay_s=0.0))
    collector.record_edge_step("AB", occupancy=2.0, queue_length=1)
    collector.record_edge_step("AB", occupancy=1.0, queue_length=0)
    collector.record_edge_entry("AB")
    collector.finalize()

    scenario_config = {"duration": 30, "seed": 123, "scale": 1.0, "beta": 1.0, "data": None}

    db_path = tmp_path / "smartflow_test.db"
    initialise_database(db_path)

    run_id = save_current_run(
        floorplan_path=floorplan_path,
        scenario_config=scenario_config,
        results=collector,
        db_path=db_path,
    )

    summary = get_run_summary(db_path, run_id)
    assert summary is not None
    assert summary["id"] == run_id
    assert summary["agent_count"] == 2
    assert summary["mean_travel_s"] is not None

    # New: run_agents aggregates via SQL.
    agg = get_run_agent_aggregates(db_path, run_id)
    assert int(agg.get("agent_count") or 0) == 2
    assert float(agg.get("avg_travel_s") or 0.0) > 0.0

    # New: top edges via SQL.
    top = get_top_edges_for_run(db_path, run_id, metric="peak_occupancy", limit=5)
    assert top
    assert top[0]["edge_id"] == "AB"

    # New: cross-run dashboard stats via SQL.
    dash = get_dashboard_stats(db_path)
    assert int(dash.get("run_count") or 0) >= 1


def test_route_cache_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "smartflow_test.db"
    initialise_database(db_path)

    payload = json.dumps(["A", "B", "C"])
    inserted = get_or_create_cached_route(
        db_path,
        layout_hash="layout123",
        origin="A",
        destination="C",
        stairs_penalty=1.0,
        key_parts=["shortest"],
        path_json=payload,
        cost=3.0,
    )
    assert inserted == payload

    fetched = get_or_create_cached_route(
        db_path,
        layout_hash="layout123",
        origin="A",
        destination="C",
        stairs_penalty=1.0,
        key_parts=["shortest"],
    )
    assert fetched == payload
