"""View for displaying simulation results."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from smartflow.io.exporters import export_pdf
from smartflow.viz.charts import build_active_agents_series, build_travel_time_histogram
from smartflow.viz.heatmap import build_heatmap_figure

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class ResultsView(ttk.Frame):
    """Frame for charts, heatmaps, and exports."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialise UI components."""
        # Header
        header = ttk.Label(self, text="Step 4: Results Analysis", font=("Segoe UI", 16, "bold"))
        header.pack(pady=(0, 20))

        # Notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tabs
        self.heatmap_tab = ttk.Frame(self.notebook)
        self.charts_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.heatmap_tab, text="Network Heatmap")
        self.notebook.add(self.charts_tab, text="Performance Charts")

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        new_run_btn = ttk.Button(nav_frame, text="< New Run", command=lambda: self.controller.show_frame("ConfigView"))
        new_run_btn.pack(side=tk.LEFT)
        
        compare_btn = ttk.Button(nav_frame, text="Compare Runs", command=lambda: self.controller.show_frame("ComparisonView"))
        compare_btn.pack(side=tk.LEFT, padx=10)
        
        self.export_btn = ttk.Button(nav_frame, text="Export PDF", command=self._export_pdf, state="disabled")
        self.export_btn.pack(side=tk.RIGHT, padx=5)
        
        self.save_btn = ttk.Button(nav_frame, text="Save Results", command=self._save_results, state="disabled")
        self.save_btn.pack(side=tk.RIGHT, padx=5)

    def update_view(self) -> None:
        """Refresh charts with latest data."""
        results = self.controller.state.get("simulation_results")
        floorplan = self.controller.state.get("floorplan")
        
        if not results or not floorplan:
            return
            
        # Enable buttons
        self.save_btn.config(state="normal")
        self.export_btn.config(state="normal")
            
        # Clear old widgets
        for widget in self.heatmap_tab.winfo_children():
            widget.destroy()
        for widget in self.charts_tab.winfo_children():
            widget.destroy()
            
        # 1. Heatmap
        try:
            graph = floorplan.to_networkx()
            fig_heatmap = build_heatmap_figure(graph, results.edge_metrics)
            canvas_heatmap = FigureCanvasTkAgg(fig_heatmap, master=self.heatmap_tab)
            canvas_heatmap.draw()
            canvas_heatmap.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            print(f"Error drawing heatmap: {e}")
            ttk.Label(self.heatmap_tab, text=f"Error loading heatmap: {e}").pack()
        
        # 2. Charts
        try:
            # Split charts tab into two columns
            chart_frame = ttk.Frame(self.charts_tab)
            chart_frame.pack(fill=tk.BOTH, expand=True)
            
            # Histogram
            fig_hist = build_travel_time_histogram(results.agent_metrics)
            canvas_hist = FigureCanvasTkAgg(fig_hist, master=chart_frame)
            canvas_hist.draw()
            canvas_hist.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Time Series
            total_ticks = 0
            if results.edge_metrics:
                first_metric = next(iter(results.edge_metrics.values()))
                total_ticks = len(first_metric.occupancy_over_time)
                
            fig_series = build_active_agents_series(results.edge_metrics, total_ticks)
            canvas_series = FigureCanvasTkAgg(fig_series, master=chart_frame)
            canvas_series.draw()
            canvas_series.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        except Exception as e:
            print(f"Error drawing charts: {e}")
            ttk.Label(self.charts_tab, text=f"Error loading charts: {e}").pack()

    def _export_pdf(self) -> None:
        """Generate and save a PDF report."""
        results = self.controller.state.get("simulation_results")
        floorplan = self.controller.state.get("floorplan")
        config = self.controller.state.get("scenario_config")
        
        if not results or not floorplan:
            return
            
        file_path = filedialog.asksaveasfilename(
            title="Export PDF Report",
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")]
        )
        
        if file_path:
            try:
                export_pdf(Path(file_path), results, floorplan, config)
                messagebox.showinfo("Export Success", f"Report saved to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to generate PDF:\n{str(e)}")

    def _save_results(self) -> None:
        """Save the current run to the database."""
        results = self.controller.state.get("simulation_results")
        floorplan_path = self.controller.state.get("floorplan_path")
        config = self.controller.state.get("scenario_config")
        
        if not results or not floorplan_path:
            return
            
        try:
            from smartflow.io.db import initialise_database, get_or_create_scenario, insert_run
            
            db_path = Path("smartflow.db")
            initialise_database(db_path)
            
            # Create scenario
            scenario_id = get_or_create_scenario(
                db_path,
                name=floorplan_path.stem,
                layout_hash=str(floorplan_path), # Simple hash for now
                config=config
            )
            
            # Prepare summary
            summary_obj = results.summary
            # Convert dataclass to dict for DB insertion
            summary = {
                "mean_travel_time_s": summary_obj.mean_travel_time_s,
                "p50_travel_time_s": summary_obj.p50_travel_time_s,
                "p90_travel_time_s": summary_obj.p90_travel_time_s,
                "p95_travel_time_s": summary_obj.p95_travel_time_s,
                "max_edge_density": summary_obj.max_edge_density,
                "congestion_events": summary_obj.congestion_events,
                "total_throughput": summary_obj.total_throughput,
                "time_to_clear_s": summary_obj.time_to_clear_s,
                "seed": config.get("seed"),
                "tick_seconds": 1.0, # Should ideally come from config
                "duration_s": config.get("duration"),
                "agent_count": len(results.agent_metrics)
            }
            
            # Prepare edge metrics
            edge_data = []
            for em in results.edge_metrics.values():
                edge_data.append({
                    "edge_id": em.edge_id,
                    "peak_occupancy": em.peak_occupancy,
                    "peak_duration_ticks": em.peak_duration_ticks,
                    "throughput_count": em.throughput_count
                })
                
            insert_run(db_path, scenario_id, summary, edge_data)
            
            messagebox.showinfo("Saved", "Results saved to database successfully.")
            self.save_btn.config(state="disabled")
            
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
