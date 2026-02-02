"""Tests for movement dynamics."""

from __future__ import annotations
import pytest
from smartflow.core import dynamics

def test_density_speed_factor() -> None:
    
    # Low density (1 person in 20m^2 = 0.05 p/m^2) -> factor should be 1.0
    factor_low = dynamics.density_speed_factor(count=1.0, length_m=10.0, width_m=2.0)
    assert factor_low == 1.0
    
    # High density (40 people in 20m^2 = 2.0 p/m^2) -> factor should be significantly lower
    factor_high = dynamics.density_speed_factor(count=40.0, length_m=10.0, width_m=2.0)
    assert factor_high < 1.0
    assert factor_high > 0.0
