"""Heatmap generation placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_heatmap_image(layout: Any, metrics: Any, output_path: Path | None = None) -> None:
    """Render a heatmap for edge occupancy across the layout graph."""

    raise NotImplementedError("Implement Matplotlib-based heatmap rendering")
