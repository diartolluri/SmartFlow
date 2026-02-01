# SmartFlow — Project Plan

A planning document for building SmartFlow: an agent-based simulation tool to analyse and improve movement flow within schools.

## 1) Overview
Schools experience heavy, synchronized movement during lesson transitions, causing congestion in corridors, stairways, and entry points. SmartFlow will simulate movement of students and staff across a school layout, producing visuals and metrics that help identify bottlenecks and test layout/schedule changes.

## 2) Objectives
- Build a Python application that loads a school floor plan and simulates agent movement between lessons.
- Identify congestion hotspots and quantify metrics (e.g., average travel time, corridor occupancy, congestion frequency/duration).
- Provide visualisations (heatmaps, charts) and an interactive GUI to run scenarios.
- Persist results (SQLite) and support exporting CSV/PDF reports.

## 3) Scope and non‑goals
- In scope:
  - Import floor plans (JSON-based graph; optional image for reference).
  - Define lesson schedules, populations, and routing rules; run agent-based simulations.
  - Visual output (charts, heatmaps) and data exports; scenario comparison in SQLite.
- Out of scope (initially):
  - 3D rendering; detailed human biomechanics; multi-building outdoor wayfinding; advanced CAD import.

## 4) Users and usage
- Facilities managers, SLT/operations staff, planners, teachers.
- Typical tasks: load layout, set schedules and student counts, run simulation, view bottlenecks, try layout tweaks, compare scenarios.

## 5) Requirements
### Functional
- Load floor plan:
  - Primary: JSON graph (nodes = junctions/rooms; edges = corridors/stairs with lengths and capacities).
  - Optional: overlay background image (PNG/JPG) for context.
- Define inputs:
  - Timetable blocks (start/end times), room locations, populations, distribution of movement (by year group/teacher), route rules.
- Simulation:
  - Agents (students/teachers) move on the graph using shortest-path routing with dynamic speeds influenced by density.
  - Support schedule-driven origin/destination per agent per period transition.
  - Time discretisation (ticks); reproducible with random seed.
- Metrics & outputs:
  - Agent-level: travel time, path length, delays.
  - Edge-level: occupancy over time, max density, time above threshold.
  - Global: mean/percentile travel times, congestion events count/duration.
  - Export CSV; persist aggregated results in SQLite; optional PDF report.
- Visualisation:
  - Heatmaps over the graph (edge occupancy/intensity).
  - Time-series charts (occupancy, travel-time distributions).
  - GUI controls: load layout, set schedules/population, run/stop, view results.

### Non-functional
- Performance: simulate ≥ 1,000 agents for a transition window (e.g., 10 minutes) within ≤ 10s on a typical laptop.
- Usability: simple GUI; sensible defaults; clear error messages.
- Portability: Windows-first; offline operation once installed.
- Testability: unit + integration tests; deterministic runs with seed.

## 6) Tech stack
- Language: Python 3.13
- Simulation: Mesa (agent-based modelling)
- Graph & routing: NetworkX
- Numerics: NumPy
- Visualisation: Matplotlib (static) + Plotly (interactive, optional)
- GUI: Tkinter for MVP (ships with Python); optional upgrade path to PySide6 for richer UI
- Persistence: SQLite (built-in sqlite3)
- Exports: CSV (built-in), PDF via ReportLab (optional)
- Packaging: requirements.txt; structured src/ package; pytest for tests

## 7) Architecture
### High-level modules
- core/
  - floorplan.py: JSON schema, load/validate, build NetworkX graph
  - agents.py: Student/Teacher agents, base movement logic
  - model.py: Mesa Model, scheduler, tick loop, metrics hooks
  - routing.py: pathfinding utilities (shortest path; weights by length/capacity)
  - dynamics.py: density-speed relationship and edge capacity logic
  - metrics.py: collectors for agent/edge/global statistics
- io/
  - importers.py: JSON loader; optional image metadata loader
  - exporters.py: CSV writers; PDF report generator (optional)
  - db.py: SQLite schema + CRUD for scenarios and results
- viz/
  - heatmap.py: edge-intensity rendering over layout (Matplotlib)
  - charts.py: time-series and distributions
- ui/
  - app.py: Tkinter main window, forms, run controls, results views
  - views/: modular frames for layout/schedule/simulation/results
- cli/
  - run_sim.py: headless run for automation
- tests/
  - unit and integration tests

### Data model (key types)
- FloorPlan (graph):
  - Node: id, label, type (junction, room, stair), position (x,y), room_capacity (opt.)
  - Edge: id, from, to, length_m, width_m, capacity_pps (people per second), is_stairs
- Agent:
  - id, type (student/teacher), speed_base, schedule (list of {period, origin_room, dest_room})
- Simulation config:
  - tick_sec, start_time, transition_window, random_seed
- Metrics:
  - per_agent: travel_time_s, path_nodes, delayed_s
  - per_edge_time: t, edge_id, occupancy, density, throughput

### Core algorithms
- Routing: Dijkstra shortest path with weight = length / width (approx.), plus stairs penalty.
- Movement & congestion:
  - Edge occupancy updated each tick; effective speed = speed_base * f(density), with e.g., linear/exponential slowdown above threshold.
  - Simple queueing when capacity exceeded; agents wait at node until edge allows entry.
- Scheduling:
  - At transition start, spawn agents per schedule; staggered departures to avoid unrealistic spikes.

## 8) File formats
### Floor plan JSON (minimal example)
```json
{
  "nodes": [
    {"id": "A", "label": "Room A", "type": "room", "pos": [0,0]},
    {"id": "B", "label": "Junction B", "type": "junction", "pos": [5,0]}
  ],
  "edges": [
    {"id": "e1", "from": "A", "to": "B", "length_m": 10, "width_m": 2, "capacity_pps": 4}
  ]
}
```

## 9) GUI flow (MVP)
1. Start app → Load floor plan JSON (with basic validation feedback)
2. Define schedule & populations (simple form: periods, rooms, counts)
3. Run simulation → progress bar → results view
4. Results: heatmap overlay + charts + CSV export; option to save scenario to SQLite

## 10) Persistence design (SQLite)
- Tables:
  - scenario(id, name, created_at, layout_hash, config_json)
  - run(id, scenario_id, started_at, seed, duration_s)
  - edge_metrics(run_id, edge_id, t, occupancy, density, throughput)
  - summary(run_id, mean_travel_s, p90_travel_s, max_edge_density, congestion_events)

## 11) Milestones (Updated Status)

### Phase 1: Core Engine & CLI (Completed)
- [x] Define JSON schema for FloorPlan and Scenario.
- [x] Implement `FloorPlan` class and NetworkX graph builder.
- [x] Implement `SmartFlowModel` (Mesa) with basic agent movement.
- [x] Implement shortest-path routing (Dijkstra/A*).
- [x] Implement density-speed dynamics (Weidmann model).
- [x] Create CLI generators (`generate_campus.py`, `generate_scenario.py`) for test data.

### Phase 2: Basic GUI & Visualization (Completed)
- [x] Build Tkinter shell (`app.py`) with navigation.
- [x] Implement `RunView` with real-time canvas visualization.
- [x] Add multi-floor support (Ground/First floor toggling).
- [x] Add visual enhancements (lateral offsets, color-coded nodes).
- [x] Implement playback speed controls.

### Phase 3: Advanced Features & Analytics (In Progress)
- [x] Implement complex agent behaviors (Toilet stops, multi-leg journeys).
- [x] Implement variable walking speeds and congestion physics.
- [ ] **Next**: Build `EditorView` for graphical floor plan design.
- [ ] **Next**: Enhance `ResultsView` with detailed per-floor metrics.
- [ ] **Next**: Add export functionality (PDF/CSV).

### Phase 4: Polish & Packaging (Future)
- [ ] Comprehensive unit testing.
- [ ] User documentation and help guides.
- [ ] Final packaging (PyInstaller).

## NEA Technique Checklist (Evidence)

- [x] Cross-table parameterised SQL
  - Evidence: [src/smartflow/io/db.py](src/smartflow/io/db.py#L159-L176), [src/smartflow/io/db.py](src/smartflow/io/db.py#L445-L456)
- [x] Graph/Tree Traversal
  - Evidence (BFS): [src/smartflow/core/graph_analysis.py](src/smartflow/core/graph_analysis.py#L20-L51)
- [x] List operations
  - Evidence (list building/slicing/aggregation): [src/smartflow/core/metrics.py](src/smartflow/core/metrics.py#L54-L105)
- [x] Stack/Queue Operations
  - Evidence (undo/redo stacks): [src/smartflow/ui/views/editor_view.py](src/smartflow/ui/views/editor_view.py#L72-L79)
  - Evidence (queue for BFS): [src/smartflow/core/graph_analysis.py](src/smartflow/core/graph_analysis.py#L34-L50)
- [x] Hashing
  - Evidence: [src/smartflow/io/db.py](src/smartflow/io/db.py#L141-L155)
- [x] Recursive algorithms
  - Evidence (recursive DFS): [src/smartflow/core/graph_analysis.py](src/smartflow/core/graph_analysis.py#L17-L68)
- [x] Complex user-defined algorithms (optimisation/minimisation/scheduling)
  - Evidence (departure-time scheduling to minimise peak departures): [src/smartflow/core/scenario_loader.py](src/smartflow/core/scenario_loader.py#L12-L57)
- [x] Mergesort or similarly efficient sort
  - Evidence (custom mergesort + use in percentiles): [src/smartflow/core/algorithms.py](src/smartflow/core/algorithms.py#L16-L97), [src/smartflow/core/metrics.py](src/smartflow/core/metrics.py#L54-L77)
- [x] Dynamic generation of objects based on complex user-defined use of OOP model
  - Evidence (generate AgentProfile objects from scenario config): [src/smartflow/core/scenario_loader.py](src/smartflow/core/scenario_loader.py#L214-L321)

## 12) Testing strategy
- Unit tests: routing weights, density-speed function, capacity/queue behaviour, JSON schema validation
- Integration: small synthetic layout with known bottleneck; verify metrics match expectations
- Performance: 1k agents within time budget; profiling hotspots (routing, occupancy updates)
- Determinism: fixed seed yields repeatable aggregate metrics within tolerance

## 13) Risks and mitigations
- Performance with large agent counts → optimise data structures; batched updates; consider NumPy arrays for edge occupancy.
- GUI complexity → start with Tkinter MVP; separate model from UI; consider PySide6 later.
- Data quality (layouts/schedules) → provide sample templates and validators with clear errors.
- Realism of behaviour → tune density-speed curve; allow simple calibration parameters.

## 14) Success criteria
- Runs a 10-minute transition for 1k agents on a mid-range laptop in ≤ 10s.
- Identifies top 3 congested edges with clear visuals and CSV outputs.
- GUI allows loading layouts, setting schedules, running, and exporting without crashes.
- Results persist and can be compared across at least two scenarios.

## 15) Proposed repo structure
```
NEA Project/
  src/smartflow/
    core/
      agents.py
      dynamics.py
      floorplan.py
      metrics.py
      model.py
      routing.py
    io/
      db.py
      exporters.py
      importers.py
    viz/
      charts.py
      heatmap.py
    ui/
      app.py
      views/
  cli/
    run_sim.py
  tests/
  data/
    samples/
      floorplan_simple.json
  requirements.txt
  README.md
```

## 16) MVP task breakdown (first 1–2 days)
- [ ] Scaffold project structure and requirements.txt
- [ ] Implement floorplan loader and NetworkX graph build
- [ ] Implement routing weights and basic shortest-path helper
- [ ] Implement simple movement with density-speed slowdown and edge capacity
- [ ] Collect basic metrics (travel times; edge occupancy over time)
- [ ] CLI runner that outputs CSV and a basic heatmap
- [ ] Add unit tests for loader, routing, and dynamics

## 17) Stretch goals
- Interactive Plotly visualisation; animation playback
- Multi-floor handling with stair capacity penalties
- Timetable import from CSV/Google Sheets
- Calibration tool to fit density-speed to observed timings

## 18) Next steps
- Confirm GUI choice (Tkinter MVP vs PySide6) and reporting (CSV-only vs PDF+CSV).
- If you’re ready, I can scaffold the structure above and add a working CLI demo next.

## 19) AQA NEA alignment and evidence plan
This section maps the plan to the typical AQA Computer Science NEA assessment headings and identifies the specific evidence to produce during the project. It also introduces traceability so every success criterion is tested and later evaluated.

- Analysis: covered by sections 1–5 and 14; add stakeholder research and alternative solutions (see section 20).
- Design: covered by sections 6–10; add explicit design artefacts (wireframes, diagrams, pseudocode – see section 22).
- Development/Technical solution: covered by sections 7, 11, 15–16; include coding standards, change log, and reuse/originality notes (see sections 21 and 26).
- Testing: covered by section 12; add a formal test plan matrix with evidence and traceability to success criteria (see section 23).
- Evaluation: add a structured evaluation against success criteria with user feedback and limitations (see section 24).
- Project management: add a dated development diary/time log (see section 21).
- Legal/ethical/accessibility: add a short analysis and controls (see section 25).
- References and licensing: add citations and license (see section 26).

### 19.1 Success criteria IDs (for traceability)
Assign stable IDs to each success criterion in section 14 for use in tests and evaluation.

- SC-1 Performance: simulate ≥ 1,000 agents for a 10-minute transition in ≤ 10s on a mid-range laptop.
- SC-2 Insights: identify the top 3 congested edges with clear visuals and CSV outputs.
- SC-3 Usability: GUI supports loading layouts, setting schedules, running, and exporting without crashes.
- SC-4 Persistence/Comparison: results persist and allow comparison across at least two scenarios.

## 20) Stakeholder requirements and research (Analysis)
Summarise user needs and the investigation that justifies SmartFlow. Capture at least one short interaction with a real or proxy stakeholder.

- Stakeholders/personas:
  - Facilities manager: needs to reduce corridor congestion between periods.
  - SLT/Timetabler: needs to test timetable and rooming scenarios quickly.
  - Teacher/Student (proxy): provides qualitative feedback on perceived bottlenecks.
- User stories and acceptance criteria:
  - As a facilities manager, I can load a floor plan and run a transition so that I can see where congestion forms. Accept: heatmap and top-3 bottleneck list exported to CSV (SC-2).
  - As a timetabler, I can adjust populations/schedules and re-run within minutes. Accept: run ≤ 10s for 1k agents; config stored for rerun (SC-1, SC-4).
  - As a user, I can operate the GUI without training. Accept: complete a basic scenario within 5 minutes; no crashes (SC-3).
- Existing/alternative approaches considered: manual observation; simple spreadsheet capacity checks; commercial simulation tools. Rationale for SmartFlow: faster iteration, reproducibility, custom metrics, school-focused data model.

Evidence to collect: brief interview/survey notes (bulleted), 1–2 photos or synthetic diagrams of a corridor layout (if permitted), and a short comparison paragraph.

## 21) Project log and time plan (Management)
Maintain a dated development diary (minimum: key sessions) and link evidence (screenshots, commits, test outputs). This supports the NEA requirement to demonstrate a systematic process.

Template (append entries during development):

| Date | Task/Feature | Key decisions/changes | Evidence (path/screenshot) | Time (h) | Next steps |
|------|--------------|-----------------------|----------------------------|----------|-----------|
| 2025-10-23 | Scaffold repo | Use Tkinter MVP; Mesa+NetworkX confirmed | screenshots/setup.png | 1.5 | Floorplan loader |

Optional: include a lightweight Gantt/roadmap image under `Other files/` and reference it here.

## 22) Design artefacts (Design)
Produce the following artefacts and store them under `Other files/Design/` (filenames in parentheses). Reference them in this plan when created.

- Context diagram (system and external actors) — `context-diagram.png`.
- Component diagram for `smartflow` modules — `components.png`.
- Data model diagram for graph and metrics — `data-model.png`.
- Key algorithms pseudocode/flowcharts: routing, density-speed, queuing — `algorithms.pdf`.
- GUI wireframes for load/run/results views — `wireframes.pdf` or `wireframes.png`.

## 23) Test plan matrix (Testing)
Define tests that demonstrate each success criterion and core behaviours. Record expected vs actual results and attach evidence (CSV snippets, screenshots, logs). Extend this table as you implement.

| Test ID | Related SC | What is tested | Method & data | Expected result | Evidence |
|---------|------------|----------------|---------------|-----------------|----------|
| T-01 | SC-1 | Performance at 1k agents/10 min | Run `cli/run_sim.py` on sample layout with 1k agents | Wall-clock ≤ 10s | timing.txt, screenshot |
| T-02 | SC-2 | Bottleneck identification | Synthetic layout with known narrow corridor | Top-3 edges include the known bottleneck; heatmap hotspot aligns | CSV snippet, heatmap.png |
| T-03 | SC-3 | GUI basic workflow | Load → configure → run → export | User completes in ≤ 5 min; no crashes | Screen recording or screenshots |
| T-04 | SC-4 | Persistence & compare | Save two scenarios; compare summaries | Summaries stored; comparison view/table generated | DB snapshot, compare.png |
| T-05 | — | Routing weights correctness | Unit tests with small graph | Shortest path matches expected weights | pytest output |
| T-06 | — | Density-speed slowdown | Unit test across densities | Speed decreases after threshold; queueing when capacity exceeded | pytest output |
| T-07 | — | Determinism with seed | Repeat run with fixed seed | Metrics within tolerance on repeats | logs.csv |

Note: Keep raw outputs in a `evidence/` folder or `Other files/` and reference their paths.

## 24) Evaluation plan (Evaluation)
Describe how you will evaluate the final system against the success criteria and reflect on fitness for purpose.

- Against SC-1: reproduce T-01 and include machine spec; discuss any variance and optimisations applied.
- Against SC-2: show the bottleneck list and heatmap; explain how insights could inform layout/timetable changes; validate on a second scenario.
- Against SC-3: capture a short user trial (proxy acceptable) and summarise feedback; note usability improvements.
- Against SC-4: demonstrate saved scenarios and comparison usefulness; discuss data persistence reliability.
- Limitations and further work: realism of movement, multi-floor complexity, data quality, UI polish.
- Maintainability and extensibility: note code structure choices, tests, and future upgrade path (e.g., PySide6, richer analytics).

## 25) Legal, ethical, accessibility, and data protection
- Data: prefer synthetic layouts. If using a real school plan, obtain permission; remove identifiers; avoid personal data. No individual tracking; only aggregate metrics.
- Security: local/offline operation; no network transmission of sensitive data.
- IP and licensing: list third-party libraries and their licenses; include a project license (e.g., MIT) in the repo.
- Accessibility: use colorblind-friendly palettes for heatmaps; ensure sufficient contrast; provide basic keyboard navigation in the GUI; avoid tiny click targets.
- Fairness/bias: ensure density-speed parameters don’t encode discriminatory assumptions; focus on physical constraints, not personal attributes.

## 26) Originality, reuse, and references
- Originality statement: core simulation logic (routing weights, density-speed, queueing, metrics, GUI integration) will be authored by the candidate.
- Reuse: permitted use of libraries (Mesa, NetworkX, NumPy, Matplotlib/Plotly, sqlite3, ReportLab). Any borrowed code snippets will be minimal and clearly cited in code comments and here.
- References: maintain a short bibliography of sources (papers, blogs, docs) that informed the design; include URLs and access dates.
- Version control evidence: retain commit history showing incremental development with meaningful messages.
