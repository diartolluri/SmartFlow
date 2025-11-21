# SmartFlow Catch-Up Roadmap

> Purpose: Concise, actionable overview of what is already implemented vs. what remains to meet the Proposal, Research, and Success Criteria you documented. Use this as your execution checklist.

---
## 1. Current Implemented Scope (Core Code)
- Floorplan Parsing & Validation: Loads JSON (`nodes`, `edges`), validates IDs, connectivity, builds `networkx.DiGraph`.
- Agent Generation: Deterministic profiles from scenario periods (single movement per agent) with sampled speed, depart jitter, penalty parameters.
- Routing: Shortest path + optional k simple alternative paths; path choice softmax over hop count; stairs penalty applied.
- Simulation Engine: Custom loop (not Mesa) with activation, per-tick movement, edge entry gating, simple slowdown based on occupancy/capacity, travel & waiting time accumulation.
- Dynamics: Basic `density_speed_factor` (power-law) & `can_enter_edge` checks (occupancy threshold).
- Metrics: Per-agent (travel_time_s, delay_s, path) and per-edge occupancy snapshots; summary: mean, p90 travel time, max occupancy, crude congestion event count.
- CLI Runner: Headless execution (`cli/run_sim.py`) producing CSVs + JSON summary.
- CSV Export Utility: Generic dictionary row writer.
- Scenario Loader: Validates minimal required keys.
- Modular Package Structure: Separation of `core`, `io`, `ui`, `viz` ready for extension.

---
## 2. Major Gaps vs Proposal & Success Criteria
| Area | Gap Summary | Impact |
|------|-------------|--------|
| GUI / Usability | Only placeholders; no workflow (load → configure → run → results) | Blocks non-technical user adoption |
| Visualization | No heatmap, no charts, no animation, no legend | Cannot highlight bottlenecks visually |
| Persistence | `io/db.py` empty; no scenario/run save/load | Cannot compare scenarios or retain history |
| Advanced Metrics | Missing density (people/m²), throughput, queue durations, bottleneck ranking, completion time, additional percentiles | Insights incomplete; decisions less evidence-based |
| Queuing Model | No explicit queue length tracking / service rate modeling | Understates delays at corridor entrances |
| Density Model Accuracy | Uses occupancy/capacity_pps (people/sec) instead of spatial density | Misrepresents true congestion levels |
| Multi-Period & Stagger | Single movement per agent; no staggered release logic | Cannot model schedule interventions |
| One-Way / Rules | No enforcement toggles or edge direction adjustments | Cannot test one-way policies |
| Rerouting Logic | Reroute fields unused; static path only | Misses adaptive behavior scenarios |
| Path Choice Cost | Softmax on hop count not weighted time | Distorts alternative route likelihood |
| Mesa Integration | Custom engine; Mesa promised in proposal | Alignment with research & plan incomplete |
| Reporting | No PDF, no export of visual assets, no scenario comparison report | Limits stakeholder communication |
| Error Handling | Limited validation for scenario movements; CLI lacks graceful messages | Risk of silent misconfiguration |
| Testing | Placeholder tests expecting NotImplemented; no functional coverage | Regressions possible, low confidence |
| Performance | No early termination; naive occupancy tracking; no profiling | Inefficient at larger scales |
| Packaging | No executable build, README gaps, no install simplicity | Deployment friction |
| Config Extensibility | No central config object or visualization settings | Harder to evolve features consistently |

---
## 3. High-Impact Immediate Tasks (Do First)
1. [x] Replace placeholder tests with real unit tests (agents, routing, dynamics, model small run). (Skipped per user request)
2. [x] Correct density model: compute density = count / (length_m * width_m); parameterize slowdown curve.
3. [x] Extend MetricsCollector: throughput per edge (entries), peak duration over threshold, time-to-clear network, queue events.
4. [x] Implement SQLite persistence: schema for scenarios, runs, edges, agents; save + load.
5. [x] Build minimal GUI workflow (tab/frame swap): Layout load, scenario configure, run with progress, results summary.
6. [x] Implement static heatmap (Matplotlib) + time-series (active agents vs ticks) + histogram (travel times).

---
## 4. Second Phase Tasks
7. [x] Add staggered release & multi-period schedule support (multiple movements per agent). 
8. [x] Implement one-way corridor toggles (mark edges disabled in reverse; UI checkbox).
9. [x] Activate rerouting: periodic check; if delay exceeds threshold choose alternative path from k list.
10. [x] Upgrade path choice: softmax over total weighted cost (sum edge weights) not hop count.
11. [x] Scenario comparison view: load two runs → diff metrics & highlight improved corridors.
12. [x] PDF Report (ReportLab): summary + top bottlenecks + charts + heatmap image export.
13. [x] Early termination & performance tweaks: stop when all agents completed; cache edge data; optional vectorization.

---
## 5. Optional / Stretch Enhancements
- Animated replay (Tkinter Canvas or Plotly frames).
- Bottleneck evolution timeline chart.
- Role differentiation (teacher vs student speed profiles & priority rules).
- Lane / left-side behavior simulation.
- Dynamic edge closures (simulate temporary blockages).
- Color/theme configuration & accessibility (high contrast mode).
- PyInstaller packaging + launcher script.
- Mesa adapter: wrap current states into Mesa `Model` & `Agent` for future extensibility.

---
## 6. Revised Data & Metrics Model (Target)
| Metric | Source Logic | Purpose |
|--------|--------------|---------|
| Travel Time (mean/p50/p90/p95/max) | Agent completion timestamps | Measure overall efficiency & extremes |
| Delay Components (waiting vs slow movement) | Separate queue wait vs speed reduction | Pinpoint cause of lateness |
| Edge Throughput (agents passed) | Increment on edge entry | Identify heavily used corridors |
| Peak Density & Duration | density >= threshold counts contiguous ticks | Detect sustained overcrowding |
| Queue Length Over Time | Agents blocked at node per edge | Capacity planning & stagger evaluation |
| Time to Clear Network | Last agent completion | Scheduling adequacy |
| Top N Bottlenecks | Rank by (peak density * duration) composite score | Intervention targeting |

Threshold suggestions (configurable):
- Free-flow density: ≤ 0.5 persons/m²
- Heavy congestion: ≥ 1.5 persons/m²
- Critical jam: ≥ 3.0 persons/m²

---
## 7. Database Schema Draft (SQLite)
Tables:
- scenarios(id PK, name TEXT, created_at, layout_hash TEXT, config_json TEXT)
- runs(id PK, scenario_id FK, started_at, seed INT, tick_seconds REAL, duration_s REAL, agents INT, mean_travel REAL, p90_travel REAL, p95_travel REAL, time_to_clear REAL)
- run_edges(run_id FK, edge_id TEXT, peak_density REAL, peak_duration_ticks INT, throughput INT, avg_density REAL, congestion_events INT)
- run_agents(run_id FK, agent_id TEXT, travel_time REAL, delay_wait REAL, delay_slow REAL, path TEXT)

Indexes: scenario_id on runs; edge_id on run_edges; agent_id on run_agents.

---
## 8. Recommended Execution Sequence (Condensed)
1. Tests + Density + Metrics foundation
2. Persistence layer
3. GUI MVP + Basic visuals
4. Advanced metrics & comparison view
5. Staggered release & multi-period
6. Rerouting & one-way policies
7. Reporting & export upgrades
8. Performance optimization & packaging
9. Optional Mesa integration & animation

---
## 9. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Metric inflation due to wrong density formula | Correct formula early; add unit tests |
| Scope creep (animation/Mesa) delays core delivery | Defer to stretch phase; freeze MVP feature set |
| GUI freeze during long runs | Run simulation in thread / use `after()` callbacks |
| Data inconsistency without persistence | Implement DB before comparison features |
| Performance issues at 1k+ agents | Early termination; profiling; simplify occupancy tracking |

---
## 10. Immediate Action Checklist
- [ ] Implement & test true density and queue metrics
- [ ] Replace placeholder tests with functional unit tests
- [ ] Create SQLite schema + scenario/save API
- [ ] Heatmap + basic charts modules
- [ ] GUI frames & navigation
- [ ] Scenario comparison data model stub

Once these are completed you will meet the majority of success criteria for functionality, usability, and analysis.

---
## 11. Quick Test Targets to Add
- Deterministic agent generation (same seed → identical first 5 agent IDs & depart times)
- Routing with stairs penalty vs without (path length difference)
- Density speed factor monotonicity (higher density → non-increasing speed)
- End-to-end tiny scenario (2 rooms, 1 corridor) travel time equals corridor length / speed_base
- Queue formation test (capacity 1, 3 agents, second agent waits ≥ 1 tick)

---
## 12. Notes on Mesa Integration (Future)
A migration path can wrap current `SmartFlowModel.step()` into Mesa scheduler calls; each `AgentRuntimeState` becomes a Mesa `Agent` with move action; data collection integrated via Mesa DataCollector. Keep abstraction boundary so current logic can remain until value proven.

---
## 13. Packaging Path
1. Ensure `requirements.txt` matches imports (add matplotlib, plotly, pillow, reportlab, sqlite3 builtin OK).
2. Add `__main__.py` for CLI convenience.
3. PyInstaller spec file with GUI entry.
4. Ship README segment with run instructions & example floorplan + scenario.

---
## 14. Floorplan & Scenario Validation Enhancements (Planned)
- Confirm every movement origin/destination exists in graph.
- Warn if destination equals origin (redundant movement).
- Validate capacity_pps consistent with width (capacity_pps ≈ width * nominal_flow_rate).
- Provide summary stats post-load: node count, edge count, average width.

---
## 15. Glossary (Quick Reference)
- Density: agents / (length_m * width_m) of edge.
- Throughput: count of successful entries into an edge.
- Queue Length: agents waiting at source node unable to enter edge.
- Time-to-clear: time when last active agent completes path.
- Bottleneck Score: peak_density * peak_duration (candidate heuristic).

---
## 16. Final Advice
Lock MVP scope (Sections 3 & 4) before starting stretch items; create small unit tests with each metric addition to avoid silent regressions; keep GUI responsive by batching chart rendering after simulation completes.

---
*End of Catch-Up Roadmap*
