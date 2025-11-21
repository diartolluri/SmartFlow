"""Density and movement dynamics models."""

from __future__ import annotations


def density_speed_factor(count: float, length_m: float, width_m: float) -> float:
    """
    Return a slowdown factor based on spatial density (people/m^2).
    
    Uses a simplified Weidmann-like fundamental diagram approach:
    - Free flow (< 0.5 p/m^2): factor = 1.0
    - Congested (> 0.5 p/m^2): linear/exponential decay
    - Jammed (> 3.0 p/m^2): factor approaches min speed (0.1)
    """
    if length_m <= 0 or width_m <= 0:
        return 0.1  # Safe fallback for invalid geometry
        
    area = length_m * width_m
    density = count / area
    
    # Thresholds based on pedestrian dynamics literature
    FREE_FLOW_LIMIT = 0.5  # p/m^2
    JAM_DENSITY = 3.5      # p/m^2
    MIN_SPEED_FACTOR = 0.1

    if density <= FREE_FLOW_LIMIT:
        return 1.0
    
    if density >= JAM_DENSITY:
        return MIN_SPEED_FACTOR
        
    # Linear interpolation between free flow and jam density
    # factor = 1.0 - (density - free) / (jam - free) * (1.0 - min)
    slope = (1.0 - MIN_SPEED_FACTOR) / (JAM_DENSITY - FREE_FLOW_LIMIT)
    factor = 1.0 - slope * (density - FREE_FLOW_LIMIT)
    
    return max(MIN_SPEED_FACTOR, factor)


def can_enter_edge(count: float, length_m: float, width_m: float, max_density: float = 3.5) -> bool:
    """
    Decide whether an agent can enter an edge based on spatial density limits.
    
    Prevents entering if the edge is physically packed (jam density).
    """
    if length_m <= 0 or width_m <= 0:
        return False
        
    area = length_m * width_m
    current_density = count / area
    
    # Allow entry only if adding one person doesn't exceed max jam density significantly
    # (Using strict check for now)
    return current_density < max_density
