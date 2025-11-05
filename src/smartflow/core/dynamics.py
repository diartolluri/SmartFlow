"""Density and movement dynamics models."""

from __future__ import annotations


def density_speed_factor(density: float, capacity: float) -> float:
    """Return a slowdown factor based on edge density vs capacity."""

    if capacity <= 0:
        raise ValueError("Capacity must be positive")
    if density <= 0:
        return 1.0
    ratio = density / capacity
    if ratio <= 1.0:
        return 1.0
    slowdown = 1.0 / (ratio ** 1.5)
    return max(0.1, slowdown)


def can_enter_edge(occupancy: float, capacity: float) -> bool:
    """Decide whether an agent can enter an edge given occupancy."""

    return occupancy < capacity
