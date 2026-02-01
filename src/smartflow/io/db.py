"""SQLite persistence layer."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


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
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                layout_hash TEXT NOT NULL,
                config_hash TEXT,
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
                p50_travel_s REAL,
                p90_travel_s REAL,
                p95_travel_s REAL,
                max_edge_density REAL,
                congestion_events INTEGER,
                total_throughput INTEGER,
                time_to_clear_s REAL,
                percent_late REAL,
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
                mean_occupancy REAL,
                peak_queue_length INTEGER,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_agents (
                run_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT,
                travel_time_s REAL,
                delay_s REAL,
                scheduled_arrival_s REAL,
                actual_arrival_s REAL,
                is_late INTEGER,
                path_json TEXT,
                PRIMARY KEY(run_id, agent_id),
                FOREIGN KEY(run_id) REFERENCES runs(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS route_cache (
                key_hash TEXT PRIMARY KEY,
                layout_hash TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                stairs_penalty REAL,
                path_json TEXT NOT NULL,
                cost REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Lightweight migrations for existing DBs (NEA-friendly: avoids destructive changes).
        _ensure_column(conn, "runs", "p50_travel_s", "REAL")
        _ensure_column(conn, "runs", "p95_travel_s", "REAL")
        _ensure_column(conn, "runs", "percent_late", "REAL")
        _ensure_column(conn, "run_edges", "mean_occupancy", "REAL")
        _ensure_column(conn, "run_edges", "peak_queue_length", "INTEGER")
        _ensure_column(conn, "scenarios", "config_hash", "TEXT")
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_edges_run ON run_edges(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_agents_run ON run_agents(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_route_cache_lookup ON route_cache(layout_hash, origin, destination)")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    """Ensure a column exists, adding it if needed.

    SQLite doesn't support `ADD COLUMN IF NOT EXISTS` on all versions, so we query
    table info first.
    """

    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def compute_layout_hash(layout_path: Path) -> str:
    """Compute a stable content hash for a layout file."""

    data = layout_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def compute_config_hash(config: Dict[str, Any]) -> str:
    """Compute a stable hash for a scenario config dict."""

    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_or_create_scenario(path: Path, name: str, layout_hash: str, config: Dict[str, Any]) -> int:
    """Retrieve existing scenario ID or create a new one."""
    
    config_str = json.dumps(config, sort_keys=True)
    config_hash = compute_config_hash(config)
    
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "SELECT id FROM scenarios WHERE name = ? AND layout_hash = ? AND config_hash = ?",
            (name, layout_hash, config_hash)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
            
        cursor = conn.execute(
            "INSERT INTO scenarios (name, layout_hash, config_hash, config_json) VALUES (?, ?, ?, ?)",
            (name, layout_hash, config_hash, config_str)
        )
        return cursor.lastrowid


def insert_run(
    path: Path, 
    scenario_id: int, 
    summary: Dict[str, Any], 
    edge_metrics: Iterable[Dict[str, Any]],
    agent_metrics: Iterable[Dict[str, Any]] | None = None,
) -> int:
    """Persist a simulation run and associated metrics."""
    
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (
                scenario_id, seed, tick_seconds, duration_s, agent_count,
                mean_travel_s, p50_travel_s, p90_travel_s, p95_travel_s,
                max_edge_density, congestion_events, total_throughput, time_to_clear_s,
                percent_late
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario_id,
                summary.get("seed"),
                summary.get("tick_seconds"),
                summary.get("duration_s") or summary.get("duration"),
                summary.get("agent_count"),
                summary.get("mean_travel_time_s"),
                summary.get("p50_travel_time_s"),
                summary.get("p90_travel_time_s"),
                summary.get("p95_travel_time_s"),
                summary.get("max_edge_density"),
                summary.get("congestion_events"),
                summary.get("total_throughput", 0),
                summary.get("time_to_clear_s"),
                summary.get("percent_late", 0.0),
            )
        )
        run_id = cursor.lastrowid
        
        edge_rows = [
            (
                run_id,
                m["edge_id"],
                m.get("peak_occupancy", 0.0),
                m.get("peak_duration_ticks", 0),
                m.get("throughput_count", 0),
                m.get("mean_occupancy", 0.0),
                m.get("peak_queue_length", 0),
            )
            for m in edge_metrics
        ]
        
        conn.executemany(
            """
            INSERT INTO run_edges (
                run_id, edge_id, peak_occupancy, peak_duration_ticks, throughput_count,
                mean_occupancy, peak_queue_length
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            edge_rows
        )

        if agent_metrics is not None:
            agent_rows = [
                (
                    run_id,
                    a.get("agent_id"),
                    a.get("role"),
                    a.get("travel_time_s"),
                    a.get("delay_s"),
                    a.get("scheduled_arrival_s"),
                    a.get("actual_arrival_s"),
                    1 if a.get("is_late") else 0,
                    a.get("path_json"),
                )
                for a in agent_metrics
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO run_agents (
                    run_id, agent_id, role, travel_time_s, delay_s,
                    scheduled_arrival_s, actual_arrival_s, is_late, path_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                agent_rows,
            )
        
        return run_id


def get_top_edges_for_run(path: Path, run_id: int, *, metric: str = "peak_occupancy", limit: int = 10) -> List[Dict[str, Any]]:
    """Return top edges for a run ordered by a metric."""

    if not path.exists():
        return []

    allowed = {"peak_occupancy", "mean_occupancy", "throughput_count", "peak_queue_length"}
    if metric not in allowed:
        raise ValueError(f"Unsupported metric: {metric}")

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"SELECT edge_id, peak_occupancy, mean_occupancy, throughput_count, peak_queue_length FROM run_edges WHERE run_id = ? ORDER BY {metric} DESC LIMIT ?",
            (int(run_id), int(limit)),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_run_agent_aggregates(path: Path, run_id: int) -> Dict[str, Any]:
    """Compute aggregate stats for agents in a run using SQL."""

    if not path.exists():
        return {}

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS agent_count,
                AVG(travel_time_s) AS avg_travel_s,
                AVG(delay_s) AS avg_delay_s,
                SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) AS late_count
            FROM run_agents
            WHERE run_id = ?
            """,
            (int(run_id),),
        ).fetchone()
        return dict(row) if row else {}


def get_dashboard_stats(path: Path) -> Dict[str, Any]:
    """Cross-run aggregate statistics for a small dashboard."""

    if not path.exists():
        return {}

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        # Aggregate stats from runs table
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS run_count,
                AVG(mean_travel_s) AS avg_mean_travel_s,
                AVG(p90_travel_s) AS avg_p90_travel_s,
                AVG(max_edge_density) AS avg_max_edge_density,
                SUM(COALESCE(total_throughput, 0)) AS total_throughput,
                AVG(percent_late) AS avg_percent_late,
                AVG(congestion_events) AS avg_congestion_events
            FROM runs
            """
        ).fetchone()
        stats = dict(row) if row else {}
        
        # Aggregate delay stats from run_agents table
        agent_row = conn.execute(
            """
            SELECT
                AVG(delay_s) AS avg_delay_s,
                SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) AS total_late_count,
                COUNT(*) AS total_agent_count
            FROM run_agents
            """
        ).fetchone()
        if agent_row:
            stats.update(dict(agent_row))
        
        return stats


def get_or_create_cached_route(
    path: Path,
    *,
    layout_hash: str,
    origin: str,
    destination: str,
    stairs_penalty: float,
    key_parts: Sequence[str],
    path_json: str | None = None,
    cost: float | None = None,
) -> Optional[str]:
    """Get a cached route by key; if `path_json` is provided, insert it.

    Returns:
        Cached `path_json` if found (or after insert), otherwise None.
    """

    key_payload = "|".join([layout_hash, origin, destination, f"{float(stairs_penalty):.4f}", *key_parts])
    key_hash = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()

    if not path.exists():
        initialise_database(path)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT path_json FROM route_cache WHERE key_hash = ?", (key_hash,)).fetchone()
        if row is not None and row["path_json"]:
            return str(row["path_json"])

        if path_json is None:
            return None

        conn.execute(
            """
            INSERT OR REPLACE INTO route_cache (
                key_hash, layout_hash, origin, destination, stairs_penalty, path_json, cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (key_hash, layout_hash, origin, destination, float(stairs_penalty), path_json, cost),
        )
        return path_json


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


def list_run_choices(path: Path) -> List[Dict[str, Any]]:
    """Return runs formatted for selection widgets (comboboxes)."""
    runs = list_all_runs(path)
    return [
        {
            "id": r.id,
            "label": f"Run {r.id} | {r.scenario_name} | {r.started_at} | {r.agent_count} agents",
        }
        for r in runs
    ]
