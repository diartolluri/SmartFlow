"""View for comparing two simulation scenarios directly."""

from __future__ import annotations

import tkinter as tk
import random
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from typing import TYPE_CHECKING, Any, Dict, Optional, List

from smartflow.io.importers import load_scenario
from smartflow.core.floorplan import load_floorplan, FloorPlan
from smartflow.core.model import SmartFlowModel, SimulationConfig
from smartflow.core.scenario_loader import create_agents_from_scenario
from smartflow.core.agents import AgentProfile, AgentScheduleEntry
from smartflow.core.metrics import AgentMetrics

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class ComparisonView(ttk.Frame):
    """Frame for selecting and comparing two scenarios by running them."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        
        self.path_a = tk.StringVar()
        self.path_b = tk.StringVar()

        # Saved-run selection (SQLite)
        self.run_a = tk.StringVar()
        self.run_b = tk.StringVar()
        self._run_choice_label_to_id: Dict[str, int] = {}
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Scenario Comparison", font=("Segoe UI Semibold", 16))
        header.pack(pady=(0, 20))

        # Selection Frame
        sel_frame = ttk.LabelFrame(self, text="Select Scenarios to Compare", padding=16)
        sel_frame.pack(fill=tk.X, pady=10)
        
        sel_frame.columnconfigure(1, weight=1)

        # Scenario A
        ttk.Label(sel_frame, text="Scenario A:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(sel_frame, textvariable=self.path_a, state="readonly").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(sel_frame, text="Browse...", command=lambda: self._browse(self.path_a)).grid(row=0, column=2, padx=5)

        # Scenario B
        ttk.Label(sel_frame, text="Scenario B:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(sel_frame, textvariable=self.path_b, state="readonly").grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(sel_frame, text="Browse...", command=lambda: self._browse(self.path_b)).grid(row=1, column=2, padx=5)
        
        # Compare Button
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.compare_btn = ttk.Button(btn_frame, text="Run & Compare Scenarios", command=self._run_comparison)
        self.compare_btn.pack()

        # Saved runs (SQLite)
        saved_frame = ttk.LabelFrame(self, text="Or Compare Saved Runs (SQLite)", padding=16)
        saved_frame.pack(fill=tk.X, pady=(0, 10))
        saved_frame.columnconfigure(1, weight=1)

        ttk.Label(saved_frame, text="Saved Run A:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.run_a_combo = ttk.Combobox(saved_frame, textvariable=self.run_a, state="readonly")
        self.run_a_combo.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(saved_frame, text="Saved Run B:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.run_b_combo = ttk.Combobox(saved_frame, textvariable=self.run_b, state="readonly")
        self.run_b_combo.grid(row=1, column=1, sticky="ew", padx=5)

        self.compare_saved_btn = ttk.Button(saved_frame, text="Compare Saved Runs", command=self._compare_saved_runs)
        self.compare_saved_btn.grid(row=0, column=2, rowspan=2, padx=5)
        
        self.status_lbl = ttk.Label(btn_frame, text="Ready.", foreground="gray")
        self.status_lbl.pack(pady=5)

        # Results Frame
        self.results_frame = ttk.LabelFrame(self, text="Comparison Results", padding=16)
        self.results_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Treeview for metrics
        columns = ("metric", "run_a", "run_b", "diff", "pct")
        self.tree = ttk.Treeview(self.results_frame, columns=columns, show="headings")
        self.tree.heading("metric", text="Metric")
        self.tree.heading("run_a", text="Scenario A")
        self.tree.heading("run_b", text="Scenario B")
        self.tree.heading("diff", text="Difference")
        self.tree.heading("pct", text="% Change")
        
        self.tree.column("metric", width=150)
        self.tree.column("run_a", width=100)
        self.tree.column("run_b", width=100)
        self.tree.column("diff", width=100)
        self.tree.column("pct", width=100)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Populate saved runs combo boxes
        self._refresh_saved_runs()
        
        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back to Results", command=lambda: self.controller.show_frame("ResultsView"))
        back_btn.pack(side=tk.LEFT)

    def update_view(self) -> None:
        """Reset state if needed."""
        self._refresh_saved_run_choices()

    def _refresh_saved_run_choices(self) -> None:
        """Populate comboboxes with runs from the SQLite DB, if present."""
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH
            from smartflow.io.db import list_run_choices

            choices = list_run_choices(DEFAULT_DB_PATH)
            labels = [c["label"] for c in choices]
            self._run_choice_label_to_id = {c["label"]: int(c["id"]) for c in choices}

            self.run_a_combo["values"] = labels
            self.run_b_combo["values"] = labels

            # Keep selections if still valid, otherwise choose the newest two.
            if labels:
                if self.run_a.get() not in self._run_choice_label_to_id:
                    self.run_a.set(labels[0])
                if self.run_b.get() not in self._run_choice_label_to_id:
                    self.run_b.set(labels[0] if len(labels) == 1 else labels[1])

            self.compare_saved_btn.config(state=("normal" if len(labels) >= 2 else "disabled"))
        except Exception:
            self.compare_saved_btn.config(state="disabled")

    def _compare_saved_runs(self) -> None:
        """Compare two runs already stored in SQLite."""
        label_a = self.run_a.get()
        label_b = self.run_b.get()
        if not label_a or not label_b:
            messagebox.showwarning("Missing Input", "Please select two saved runs.")
            return
        if label_a == label_b:
            messagebox.showwarning("Invalid Selection", "Please select two different runs.")
            return

        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH
            from smartflow.io.db import get_run_summary

            run_id_a = self._run_choice_label_to_id.get(label_a)
            run_id_b = self._run_choice_label_to_id.get(label_b)
            if run_id_a is None or run_id_b is None:
                raise ValueError("Selected run could not be resolved.")

            row_a = get_run_summary(DEFAULT_DB_PATH, int(run_id_a))
            row_b = get_run_summary(DEFAULT_DB_PATH, int(run_id_b))
            if not row_a or not row_b:
                raise ValueError("Could not load one or both runs from the database.")

            metrics_a = {
                "mean_travel_s": float(row_a.get("mean_travel_s") or 0.0),
                "p90_travel_s": float(row_a.get("p90_travel_s") or 0.0),
                "max_edge_density": float(row_a.get("max_edge_density") or 0.0),
                "congestion_events": float(row_a.get("congestion_events") or 0.0),
                "total_throughput": float(row_a.get("total_throughput") or 0.0),
                "time_to_clear_s": float(row_a.get("time_to_clear_s") or 0.0),
            }
            metrics_b = {
                "mean_travel_s": float(row_b.get("mean_travel_s") or 0.0),
                "p90_travel_s": float(row_b.get("p90_travel_s") or 0.0),
                "max_edge_density": float(row_b.get("max_edge_density") or 0.0),
                "congestion_events": float(row_b.get("congestion_events") or 0.0),
                "total_throughput": float(row_b.get("total_throughput") or 0.0),
                "time_to_clear_s": float(row_b.get("time_to_clear_s") or 0.0),
            }

            self.status_lbl.config(text="Compared saved runs.", foreground="green")
            self._display_results(metrics_a, metrics_b)

        except Exception as e:
            messagebox.showerror("Database Error", str(e))
            self.status_lbl.config(text="Error occurred.", foreground="red")

    def _refresh_saved_runs(self) -> None:
        """Fetch available runs from SQLite and populate dropdowns."""
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH
            path = Path(DEFAULT_DB_PATH)
            if not path.exists():
                return
                
            import sqlite3
            with sqlite3.connect(path) as conn:
                cursor = conn.execute("""
                    SELECT r.id, s.name, r.started_at, r.agent_count 
                    FROM runs r 
                    JOIN scenarios s ON r.scenario_id = s.id 
                    ORDER BY r.id DESC
                """)
                runs = cursor.fetchall()
                
            self._run_choice_label_to_id = {}
            labels = []
            for r in runs:
                # Format: "Run #12 - MyScenario (2026-02-02 10:00) - 500 agents"
                label = f"Run #{r[0]} - {r[1]} ({r[2]}) - {r[3]} agents"
                self._run_choice_label_to_id[label] = r[0]
                labels.append(label)
                
            self.run_a_combo["values"] = labels
            self.run_b_combo["values"] = labels
            
        except Exception as e:
            print(f"Failed to load saved runs: {e}")

    def _compare_saved_runs(self) -> None:
        """Load data for two selected saved runs and display comparison."""
        lbl_a = self.run_a.get()
        lbl_b = self.run_b.get()
        
        if not lbl_a or not lbl_b:
            messagebox.showwarning("Selection Missing", "Please select two runs to compare.")
            return
            
        id_a = self._run_choice_label_to_id.get(lbl_a)
        id_b = self._run_choice_label_to_id.get(lbl_b)
        
        if id_a is None or id_b is None:
            return

        from smartflow.io.persistence import DEFAULT_DB_PATH
        from smartflow.io import db
        
        try:
            data_a, data_b = db.get_comparison_data(Path(DEFAULT_DB_PATH), id_a, id_b)
            if data_a and data_b:
                self._display_comparison(data_a, data_b)
            else:
                messagebox.showerror("Error", "Could not load data for one or more runs.")
        except Exception as e:
            messagebox.showerror("Error", f"Database error: {e}")

    def _display_comparison(self, a: Dict[str, Any], b: Dict[str, Any]) -> None:
        """Populate the TreeView with side-by-side metrics."""
        
        # clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Define metrics to compare
        # (Label, Key, LowerIsBetter?)
        metrics_map = [
            ("Mean Travel Time (s)", "mean_travel_s", True),
            ("90th Percentile Time (s)", "p90_travel_s", True),
            ("Time to Clear School (s)", "time_to_clear_s", True),
            ("Total throughput", "agent_count", False),
            ("Max Edge Density (p/m²)", "max_edge_density", True),
            ("Late Students (%)", "percent_late", True),
            ("Congestion Events", "congestion_events", True),
        ]
        
        for label, key, lower_is_better in metrics_map:
            val_a = float(a.get(key, 0) or 0)
            val_b = float(b.get(key, 0) or 0)
            
            diff = val_b - val_a
            
            if val_a != 0:
                pct = (diff / val_a) * 100
                pct_str = f"{pct:+.1f}%"
            else:
                pct_str = "N/A"
                
            diff_str = f"{diff:+.2f}"
            
            # Determine "improvement" colour (green if better, red if worse)
            # If LowerIsBetter: Negative Diff = Green (Good)
            # If HigherIsBetter: Positive Diff = Green (Good)
            is_improvement = (diff < 0) if lower_is_better else (diff > 0)
            is_neutral = (abs(diff) < 0.001)
            
            # Note: Treeview tags logic would go here for colouring rows
            
            self.tree.insert("", "end", values=(
                label,
                f"{val_a:.2f}",
                f"{val_b:.2f}",
                diff_str,
                pct_str
            ))

        # --- Calculate Overall Efficiency Score ---
        # Efficiency is an abstract score (0-100) combining flow speed, punctuality, and throughput.
        # Higher is better.
        
        def calculate_efficiency(data: Dict[str, Any]) -> float:
            mean_time = float(data.get("mean_travel_s", 60.0) or 60.0)
            percent_late = float(data.get("percent_late", 0.0) or 0.0)
            throughput = float(data.get("agent_count", 0.0) or 0.0)
            congestion = float(data.get("max_edge_density", 0.0) or 0.0)

            # Heuristic weights for a "School Efficiency Score":
            # 1. Punctuality is king (large penalty for lateness)
            # 2. Movement speed is secondary (penalty for long travel time)
            # 3. Safety (congestion penalty)
            
            # Base score: 100
            score = 100.0
            
            # Penalize lateness heavily: lose 1 point for every 1% of students late
            score -= (percent_late * 1.0)
            
            # Penalize excessive travel time (baseline expected is 60s)
            extra_time = max(0.0, mean_time - 60.0)
            score -= (extra_time * 0.2)
            
            # Penalize dangerous congestion (density > 2.0 p/m2 is bad)
            if congestion > 2.0:
                score -= (congestion * 5.0)

            return max(0.0, min(100.0, score))

        eff_a = calculate_efficiency(a)
        eff_b = calculate_efficiency(b)
        eff_diff = eff_b - eff_a
        eff_pct = ((eff_diff / eff_a) * 100) if eff_a > 0 else 0.0

        # Insert Divider
        self.tree.insert("", "end", values=("", "", "", "", ""))
        
        # Insert Efficiency Row
        self.tree.insert("", "end", values=(
            "OVERALL EFFICIENCY SCORE",
            f"{eff_a:.1f}",
            f"{eff_b:.1f}",
            f"{eff_diff:+.1f}",
            f"{eff_pct:+.1f}%"
        ), tags=("efficiency",))
        
        # Style the efficiency row
        self.tree.tag_configure("efficiency", font=("Segoe UI", 10, "bold"), background="#e1f5fe")

    def _browse(self, var: tk.StringVar) -> None:
        filename = filedialog.askopenfilename(
            title="Select Scenario File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialdir=Path.cwd() / "data" / "samples"
        )
        if filename:
            var.set(filename)

    def _run_comparison(self) -> None:
        """Run both scenarios and compare results."""
        path_a = self.path_a.get()
        path_b = self.path_b.get()
        
        if not path_a or not path_b:
            messagebox.showwarning("Missing Input", "Please select two scenario files.")
            return
            
        self.compare_btn.config(state="disabled")
        self.status_lbl.config(text="Running Scenario A...", foreground="blue")
        self.update_idletasks()
        
        try:
            # Run A
            metrics_a = self._run_headless(Path(path_a))
            
            self.status_lbl.config(text="Running Scenario B...", foreground="blue")
            self.update_idletasks()
            
            # Run B
            metrics_b = self._run_headless(Path(path_b))
            
            self.status_lbl.config(text="Comparison Complete.", foreground="green")
            self._display_results(metrics_a, metrics_b)
            
        except Exception as e:
            messagebox.showerror("Simulation Error", f"Failed to run simulation: {e}")
            self.status_lbl.config(text="Error occurred.", foreground="red")
        finally:
            self.compare_btn.config(state="normal")

    def _run_headless(self, path: Path) -> Dict[str, float]:
        """Load and run a scenario (or layout) without GUI visualisation."""
        
        floorplan = None
        agents = []
        sim_config = None
        duration = 300.0
        
        # 1. Try to load as Scenario
        try:
            scenario_data = load_scenario(path)
            
            # Found a scenario, now find the layout
            layout_name = path.stem.replace("_scenario", "")
            layout_path = path.with_name(f"{layout_name}.json")
            
            if not layout_path.exists():
                layout_path = path.with_name(f"{path.stem}.json")
                
            if not layout_path.exists():
                raise FileNotFoundError(f"Could not find layout file for {path.name}")
                
            floorplan = load_floorplan(layout_path)
            
            duration = float(scenario_data.get("transition_window_s", 300))
            seed = int(scenario_data.get("random_seed", 42))
            
            sim_config = SimulationConfig(
                tick_seconds=0.1,
                transition_window_s=duration,
                random_seed=seed
            )
            
            agents = create_agents_from_scenario(scenario_data, floorplan)
            
        except ValueError:
            # 2. Not a scenario (missing keys), try to load as Layout
            try:
                floorplan = load_floorplan(path)
                
                # It's a layout! Generate default random scenario
                seed = 42
                duration = 300.0
                
                sim_config = SimulationConfig(
                    tick_seconds=0.1,
                    transition_window_s=duration,
                    random_seed=seed
                )
                
                # Generate random agents
                agents = self._generate_random_agents(floorplan, count=50, seed=seed)
                
            except Exception as e:
                raise ValueError(f"File is neither a valid scenario nor a layout: {e}")

        # 3. Model
        model = SmartFlowModel(floorplan, agents, sim_config)
        
        # 4. Run Loop
        total_ticks = int(duration / 0.1)
        for _ in range(total_ticks):
            model.step()
            if model.is_complete:
                break
            
        # 5. Collect Metrics
        for state in model.agents:
             # Identify role (e.g. diligent/relaxed) if we can map it back from profile
             # For now, just pass the profile role
             role = state.profile.role if hasattr(state.profile, "role") else "student"
             
             model.collector.record_agent(
                state.profile.agent_id,
                AgentMetrics(
                    travel_time_s=state.travel_time_s,
                    path_nodes=state.path_nodes,
                    delay_s=state.waiting_time_s,
                    scheduled_arrival_s=state.profile.schedule[-1].depart_time_s if state.profile.schedule else 0.0,
                    actual_arrival_s=(state.profile.schedule[0].depart_time_s if state.profile.schedule else 0.0) + state.travel_time_s,
                    is_late=state.is_late,
                    role=role
                )
            )
            
        summary = model.collector.finalize()
        
        return {
            "mean_travel_s": summary.mean_travel_time_s or 0.0,
            "p90_travel_s": summary.p90_travel_time_s or 0.0,
            "max_edge_density": summary.max_edge_density or 0.0,
            "congestion_events": summary.congestion_events or 0,
            "total_throughput": summary.total_throughput,
            "time_to_clear_s": summary.time_to_clear_s or 0.0
        }

    def _generate_random_agents(self, floorplan: FloorPlan, count: int, seed: int) -> List[AgentProfile]:
        """Generate random agents for a layout."""
        rng = random.Random(seed)
        nodes = list(floorplan.node_ids())
        
        if not nodes:
            return []
            
        agents = []
        for i in range(count):
            origin = rng.choice(nodes)
            dest = rng.choice(nodes)
            while dest == origin and len(nodes) > 1:
                dest = rng.choice(nodes)
                
            entry = AgentScheduleEntry(
                period="Random",
                origin_room=origin,
                destination_room=dest,
                depart_time_s=rng.uniform(0, 60)
            )
            
            profile = AgentProfile(
                agent_id=f"student_{i}",
                role="student",
                speed_base_mps=rng.normalvariate(1.4, 0.2),
                stairs_penalty=0.5,
                optimality_beta=rng.normalvariate(1.0, 0.2), # Variable beta!
                reroute_interval_ticks=10,
                detour_probability=0.1,
                schedule=[entry]
            )
            agents.append(profile)
        return agents

    def _display_results(self, data_a: Dict[str, float], data_b: Dict[str, float]) -> None:
        self.tree.delete(*self.tree.get_children())
        
        metrics = [
            ("Mean Travel (s)", "mean_travel_s", False),
            ("P90 Travel (s)", "p90_travel_s", False),
            ("Max Density", "max_edge_density", False),
            ("Congestion Events", "congestion_events", False),
            ("Throughput", "total_throughput", True),
            ("Time to Clear (s)", "time_to_clear_s", False)
        ]
        
        for label, key, higher_better in metrics:
            val_a = data_a.get(key, 0.0)
            val_b = data_b.get(key, 0.0)
            
            diff = val_b - val_a
            if val_a != 0:
                pct = (diff / val_a) * 100
            else:
                pct = 0.0
                
            tag = ""
            if diff == 0:
                tag = "neutral"
            elif (diff < 0 and not higher_better) or (diff > 0 and higher_better):
                tag = "good"
            else:
                tag = "bad"
                
            self.tree.insert(
                "",
                tk.END,
                values=(
                    label,
                    f"{val_a:.2f}",
                    f"{val_b:.2f}",
                    f"{diff:+.2f}",
                    f"{pct:+.1f}%"
                ),
                tags=(tag,)
            )
            
        self.tree.tag_configure("good", foreground="green")
        self.tree.tag_configure("bad", foreground="red")
