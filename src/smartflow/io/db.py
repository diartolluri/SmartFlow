"""SQLite persistence layer scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ScenarioRecord:
    name: str
    layout_hash: str
    config_json: str


def initialise_database(path: Path) -> None:
    """Create required tables if they do not exist."""

    raise NotImplementedError("Create database schema")


def insert_run(path: Path, scenario_id: int, summary: dict, edge_rows: Iterable[dict]) -> None:
    """Persist a simulation run and associated metrics."""

    raise NotImplementedError("Implement run persistence")
