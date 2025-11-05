# SmartFlow

SmartFlow is an agent-based simulation tool for analysing corridor congestion during school timetable transitions. This repository currently provides a scaffold aligned with the `PLAN.md` document so you can implement the NEA solution incrementally.

## Repository layout

```
src/smartflow/
  core/           # Simulation logic: floorplans, agents, model, routing, dynamics, metrics
  io/             # Import/export helpers, database persistence stubs
  viz/            # Plotting and heatmap utilities
  ui/             # Tkinter application shell with modular views
cli/run_sim.py    # Headless CLI entry point (stub)
tests/            # Pytest scaffold with placeholder tests
data/samples/     # Example layout and scenario JSON files
```

## Getting started

```bash
python -m pip install -r requirements.txt
pytest
```

Both commands currently fail because the implementation stubs raise `NotImplementedError`. Replace the placeholder logic with working code as you progress through the milestones in `PLAN.md`.

## Next steps

1. Implement `smartflow.core.floorplan.load_floorplan` to read `data/samples/floorplan_simple.json` into a NetworkX graph.
2. Flesh out agent generation and routing logic.
3. Wire `cli/run_sim.py` to the simulation pipeline for repeatable runs.
4. Expand the Tkinter UI with layout loading, configuration, and results panels.

Keep the NEA evidence (screenshots, logs, stakeholder notes) under `docs/` as described in the plan.
