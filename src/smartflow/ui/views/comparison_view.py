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
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Scenario Comparison", font=("Segoe UI", 16, "bold"))
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
        
        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back to Results", command=lambda: self.controller.show_frame("ResultsView"))
        back_btn.pack(side=tk.LEFT)

    def update_view(self) -> None:
        """Reset state if needed."""
        pass

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
             model.collector.record_agent(
                state.profile.agent_id,
                AgentMetrics(
                    travel_time_s=state.travel_time_s,
                    path_nodes=state.path_nodes,
                    delay_s=state.waiting_time_s,
                    scheduled_arrival_s=state.profile.schedule[0].depart_time_s + 0, # Approx
                    actual_arrival_s=state.profile.schedule[0].depart_time_s + state.travel_time_s,
                    is_late=False # Logic needs refinement but this prevents crash
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
