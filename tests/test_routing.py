"""Tests for routing helpers (placeholders)."""

from importlib import import_module


def test_choose_route_not_implemented() -> None:
    routing = import_module("smartflow.core.routing")
    try:
        routing.choose_route([], beta=1.0)
    except NotImplementedError:
        pass
    else:
        raise AssertionError("choose_route should be implemented during development")
