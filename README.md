# SmartFlow

SmartFlow is an agent-based simulation tool for analysing corridor congestion during school timetable transitions. It simulates student movement across a multi-floor campus layout, providing real-time visualization and detailed metrics to help identify bottlenecks.

## Features

*   **Multi-Floor Simulation**: Supports complex layouts with multiple floors, stairs, and outdoor paths.
*   **Realistic Agent Behavior**:
    *   **Variable Speeds**: Students walk at different speeds based on a normal distribution.
    *   **Complex Schedules**: Supports multi-leg journeys (e.g., Class -> Toilet -> Class) with realistic delays.
    *   **Congestion Physics**: Walking speed dynamically reduces as corridor density increases.
    *   **Free-Flowing Movement**: Agents use the full width of corridors and have lateral offsets for realistic visualization.
*   **Interactive Visualization**:
    *   Real-time 2D map with floor toggling (Ground/First Floor).
    *   Color-coded nodes (Green=Entry, Orange=Exit, Pink=Toilets).
    *   Playback speed control.
*   **Data-Driven**:
    *   Layouts and scenarios defined in JSON.
    *   Includes CLI tools to generate complex test data programmatically.
*   **Analysis**:
    *   Heatmaps of congestion hotspots.
    *   Charts for travel time distribution and corridor usage.

## Repository layout

```
src/smartflow/
  core/           # Simulation logic: floorplans, agents, model, routing, dynamics, metrics
  io/             # Import/export helpers, database persistence
  viz/            # Plotting and heatmap utilities
  ui/             # Tkinter application shell with modular views
cli/              # Command-line tools
  generate_campus.py   # Generates the multi-floor school layout
  generate_scenario.py # Generates realistic student schedules
  run_sim.py           # Headless CLI entry point
tests/            # Pytest suite
data/samples/     # Generated layout and scenario JSON files
```

## Getting started

1.  **Install Dependencies**:
    ```bash
    python -m pip install -r requirements.txt
    ```

2.  **Generate Test Data**:
    Run the generator scripts to create the campus layout and student scenarios:
    ```bash
    python cli/generate_campus.py
    python cli/generate_scenario.py
    ```

3.  **Run the Application**:
    ```bash
    python run_gui.py
    ```

4.  **Run a Simulation**:
    *   Go to the **Run Simulation** tab.
    *   Click **Load Scenario** and select `data/samples/scenario_school.json`.
    *   Click **Start Simulation**.
    *   Use the **Floor View** radio buttons to switch between floors.

## Next steps

1.  Implement the **Floor Plan Editor** to allow users to design layouts graphically.
2.  Refine the **Results View** to provide more detailed per-floor analytics.
3.  Add support for **Emergency Evacuation** scenarios.

Keep the NEA evidence (screenshots, logs, stakeholder notes) under `docs/` as described in the plan.
