"""Tests for movement dynamics (placeholders)."""

from importlib import import_module


def test_density_speed_factor_not_implemented() -> None:
    dynamics = import_module("smartflow.core.dynamics")
    try:
        dynamics.density_speed_factor(0.0, 1.0)
    except NotImplementedError:
        pass
    else:
        raise AssertionError("density_speed_factor should be implemented during development")
