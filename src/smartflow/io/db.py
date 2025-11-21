"""SQLite persistence layer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ScenarioRecord:
    id: int
    name: str
    layout_hash: str
    config_json: str
    created_at: str


@dataclass
class RunRecord:
    id: int
    scenario_name: str
    started_at: str
    agent_count: int
    duration_s: float
    mean_travel_s: float


def initialise_database(path: Path) -> None:
    """Create required tables if they do not exist."""
    
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                layout_hash TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                seed INTEGER,
                tick_seconds REAL,
                duration_s REAL,
                agent_count INTEGER,
                mean_travel_s REAL,
                p90_travel_s REAL,
                max_edge_density REAL,
                congestion_events INTEGER,
                total_throughput INTEGER,
                time_to_clear_s REAL,
                FOREIGN KEY(scenario_id) REFERENCES scenarios(id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_edges (
                run_id INTEGER NOT NULL,
                edge_id TEXT NOT NULL,
                peak_occupancy REAL,
                peak_duration_ticks INTEGER,
                throughput_count INTEGER,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_edges_run ON run_edges(run_id)")


def get_or_create_scenario(path: Path, name: str, layout_hash: str, config: Dict[str, Any]) -> int:
    """Retrieve existing scenario ID or create a new one."""
    
    config_str = json.dumps(config, sort_keys=True)
    
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "SELECT id FROM scenarios WHERE name = ? AND layout_hash = ? AND config_json = ?",
            (name, layout_hash, config_str)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
            
        cursor = conn.execute(
            "INSERT INTO scenarios (name, layout_hash, config_json) VALUES (?, ?, ?)",
            (name, layout_hash, config_str)
        )
        return cursor.lastrowid


def insert_run(
    path: Path, 
    scenario_id: int, 
    summary: Dict[str, Any], 
    edge_metrics: Iterable[Dict[str, Any]]
) -> int:
    """Persist a simulation run and associated metrics."""
    
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (
                scenario_id, seed, tick_seconds, duration_s, agent_count,
                mean_travel_s, p90_travel_s, max_edge_density, 
                congestion_events, total_throughput, time_to_clear_s
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario_id,
                summary.get("seed"),
                summary.get("tick_seconds"),
                summary.get("duration_s"),
                summary.get("agent_count"),
                summary.get("mean_travel_time_s"),
                summary.get("p90_travel_time_s"),
                summary.get("max_edge_density"),
                summary.get("congestion_events"),
                summary.get("total_throughput", 0),
                summary.get("time_to_clear_s")
            )
        )
        run_id = cursor.lastrowid
        
        edge_rows = [
            (
                run_id,
                m["edge_id"],
                m.get("peak_occupancy", 0.0),
                m.get("peak_duration_ticks", 0),
                m.get("throughput_count", 0)
            )
            for m in edge_metrics
        ]
        
        conn.executemany(
            """
            INSERT INTO run_edges (
                run_id, edge_id, peak_occupancy, peak_duration_ticks, throughput_count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            edge_rows
        )
        
        return run_id


def list_scenarios(path: Path) -> List[ScenarioRecord]:
    """List all saved scenarios."""
    if not path.exists():
        return []
        
    with sqlite3.connect(path) as conn:
        cursor = conn.execute("SELECT id, name, layout_hash, config_json, created_at FROM scenarios ORDER BY created_at DESC")
        return [
            ScenarioRecord(
                id=row[0],
                name=row[1],
                layout_hash=row[2],
                config_json=row[3],
                created_at=row[4]
            )
            for row in cursor.fetchall()
        ]


def get_run_summary(path: Path, run_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve summary stats for a specific run."""
    if not path.exists():
        return None
        
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def list_all_runs(path: Path) -> List[RunRecord]:
    """List all runs with their scenario names."""
    if not path.exists():
        return []
        
    with sqlite3.connect(path) as conn:
        query = """
            SELECT r.id, s.name, r.started_at, r.agent_count, r.duration_s, r.mean_travel_s
            FROM runs r
            JOIN scenarios s ON r.scenario_id = s.id
            ORDER BY r.started_at DESC
        """
        cursor = conn.execute(query)
        return [
            RunRecord(
                id=row[0],
                scenario_name=row[1],
                started_at=row[2],
                agent_count=row[3],
                duration_s=row[4],
                mean_travel_s=row[5]
            )
            for row in cursor.fetchall()
        ]
