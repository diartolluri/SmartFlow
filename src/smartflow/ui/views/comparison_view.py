"""View for comparing two simulation runs."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Dict

from smartflow.io.db import list_all_runs, get_run_summary

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class ComparisonView(ttk.Frame):
    """Frame for selecting and comparing two runs."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        self.db_path = Path("smartflow.db")
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Scenario Comparison", font=("Segoe UI", 16, "bold"))
        header.pack(pady=(0, 20))

        # Selection Frame
        sel_frame = ttk.LabelFrame(self, text="Select Runs", padding=16)
        sel_frame.pack(fill=tk.X, pady=10)
        
        sel_frame.columnconfigure(1, weight=1)
        sel_frame.columnconfigure(3, weight=1)

        # Run A
        ttk.Label(sel_frame, text="Run A (Baseline):").grid(row=0, column=0, sticky="w", padx=5)
        self.run_a_combo = ttk.Combobox(sel_frame, state="readonly", width=40)
        self.run_a_combo.grid(row=0, column=1, sticky="ew", padx=5)

        # Run B
        ttk.Label(sel_frame, text="Run B (Comparison):").grid(row=0, column=2, sticky="w", padx=5)
        self.run_b_combo = ttk.Combobox(sel_frame, state="readonly", width=40)
        self.run_b_combo.grid(row=0, column=3, sticky="ew", padx=5)
        
        # Compare Button
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="Compare Metrics", command=self._compare_runs).pack()

        # Results Frame
        self.results_frame = ttk.LabelFrame(self, text="Comparison Results", padding=16)
        self.results_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Treeview for metrics
        columns = ("metric", "run_a", "run_b", "diff", "pct")
        self.tree = ttk.Treeview(self.results_frame, columns=columns, show="headings")
        self.tree.heading("metric", text="Metric")
        self.tree.heading("run_a", text="Run A")
        self.tree.heading("run_b", text="Run B")
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
        """Refresh the run lists."""
        runs = list_all_runs(self.db_path)
        
        # Format: "ID: Name (Date)"
        values = [f"{r.id}: {r.scenario_name} ({r.started_at})" for r in runs]
        
        self.run_a_combo["values"] = values
        self.run_b_combo["values"] = values
        
        if values:
            self.run_a_combo.current(0)
            if len(values) > 1:
                self.run_b_combo.current(1)
            else:
                self.run_b_combo.current(0)

    def _compare_runs(self) -> None:
        """Calculate and display differences."""
        sel_a = self.run_a_combo.get()
        sel_b = self.run_b_combo.get()
        
        if not sel_a or not sel_b:
            return
            
        id_a = int(sel_a.split(":")[0])
        id_b = int(sel_b.split(":")[0])
        
        data_a = get_run_summary(self.db_path, id_a)
        data_b = get_run_summary(self.db_path, id_b)
        
        if not data_a or not data_b:
            return
            
        self.tree.delete(*self.tree.get_children())
        
        metrics = [
            ("Mean Travel (s)", "mean_travel_s", False), # False = lower is better
            ("P90 Travel (s)", "p90_travel_s", False),
            ("Max Density", "max_edge_density", False),
            ("Congestion Events", "congestion_events", False),
            ("Throughput", "total_throughput", True), # True = higher is better
            ("Time to Clear (s)", "time_to_clear_s", False)
        ]
        
        for label, key, higher_better in metrics:
            val_a = float(data_a.get(key, 0))
            val_b = float(data_b.get(key, 0))
            
            diff = val_b - val_a
            if val_a != 0:
                pct = (diff / val_a) * 100
            else:
                pct = 0.0
                
            # Color coding
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
