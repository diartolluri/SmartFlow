"""View for displaying simulation results."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from smartflow.io.exporters import export_pdf
from smartflow.viz.charts import build_active_agents_series, build_top_edges_bar, build_travel_time_histogram
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
        self.dashboard_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.heatmap_tab, text="Network Heatmap")
        self.notebook.add(self.charts_tab, text="Performance Charts")
        self.notebook.add(self.dashboard_tab, text="DB Dashboard")

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
        auto_saved = bool(self.controller.state.get("last_run_auto_saved"))
        self.save_btn.config(state=("disabled" if auto_saved else "normal"))
        self.export_btn.config(state="normal")
            
        # Clear old widgets
        for widget in self.heatmap_tab.winfo_children():
            widget.destroy()
        for widget in self.charts_tab.winfo_children():
            widget.destroy()
        for widget in self.dashboard_tab.winfo_children():
            widget.destroy()
            
        # 1. Heatmaps (multi-floor)
        try:
            graph = floorplan.to_networkx()
            floors = sorted({int(data.get("floor", 0)) for _, data in graph.nodes(data=True)})
            if not floors:
                floors = [0]

            heatmap_notebook = ttk.Notebook(self.heatmap_tab)
            heatmap_notebook.pack(fill=tk.BOTH, expand=True)

            # All floors
            all_tab = ttk.Frame(heatmap_notebook)
            heatmap_notebook.add(all_tab, text="All")
            fig_all = build_heatmap_figure(graph, results.edge_metrics, title="Congestion Heatmap (All)")
            canvas_all = FigureCanvasTkAgg(fig_all, master=all_tab)
            canvas_all.draw()
            canvas_all.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Per-floor
            for f in floors:
                tab = ttk.Frame(heatmap_notebook)
                heatmap_notebook.add(tab, text=("Ground" if f == 0 else f"Floor {f}"))
                fig_floor = build_heatmap_figure(
                    graph,
                    results.edge_metrics,
                    title=(f"Congestion Heatmap — Floor {f}"),
                    floor=int(f),
                )
                canvas_floor = FigureCanvasTkAgg(fig_floor, master=tab)
                canvas_floor.draw()
                canvas_floor.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        except Exception as e:
            print(f"Error drawing heatmaps: {e}")
            ttk.Label(self.heatmap_tab, text=f"Error loading heatmaps: {e}").pack()
        
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

        # 3. DB dashboard + analytics
        try:
            self._build_dashboard(results, floorplan)
        except Exception as e:
            ttk.Label(self.dashboard_tab, text=f"Error loading dashboard: {e}").pack(anchor="w")


    def _build_dashboard(self, results, floorplan) -> None:
        """Render a simple dashboard from SQL aggregates + graph analytics."""

        header = ttk.Label(self.dashboard_tab, text="Saved Runs Dashboard", font=("Segoe UI", 12, "bold"))
        header.pack(anchor="w", pady=(0, 10))

        # --- SQL aggregates ---
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH
            from smartflow.io import db as dbio

            stats = dbio.get_dashboard_stats(DEFAULT_DB_PATH)
            stats_frame = ttk.LabelFrame(self.dashboard_tab, text="Database Overview (SQL aggregates)", padding=12)
            stats_frame.pack(fill=tk.X, pady=(0, 10))

            def kv_row(parent, label: str, value) -> None:
                row = ttk.Frame(parent)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=f"{label}:", width=24).pack(side=tk.LEFT)
                ttk.Label(row, text=str(value)).pack(side=tk.LEFT)

            kv_row(stats_frame, "Run count", int(stats.get("run_count") or 0))
            kv_row(stats_frame, "Avg mean travel (s)", round(float(stats.get("avg_mean_travel_s") or 0.0), 2))
            kv_row(stats_frame, "Avg p90 travel (s)", round(float(stats.get("avg_p90_travel_s") or 0.0), 2))
            kv_row(stats_frame, "Avg max edge density", round(float(stats.get("avg_max_edge_density") or 0.0), 3))
            kv_row(stats_frame, "Total throughput", int(stats.get("total_throughput") or 0))

            run_id = self.controller.state.get("last_run_id")
            if run_id:
                per_run = ttk.LabelFrame(self.dashboard_tab, text=f"Latest Run (ID {run_id})", padding=12)
                per_run.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

                agg = dbio.get_run_agent_aggregates(DEFAULT_DB_PATH, int(run_id))
                kv_row(per_run, "Agents", int(agg.get("agent_count") or 0))
                kv_row(per_run, "Avg travel (s)", round(float(agg.get("avg_travel_s") or 0.0), 2))
                kv_row(per_run, "Avg delay (s)", round(float(agg.get("avg_delay_s") or 0.0), 2))
                kv_row(per_run, "Late count", int(agg.get("late_count") or 0))

                top_edges = dbio.get_top_edges_for_run(DEFAULT_DB_PATH, int(run_id), metric="peak_occupancy", limit=8)
                if top_edges:
                    ttk.Label(per_run, text="Top edges by peak occupancy:").pack(anchor="w", pady=(8, 2))
                    items = [
                        (str(r.get("edge_id")), float(r.get("peak_occupancy") or 0.0))
                        for r in top_edges
                    ]
                    fig = build_top_edges_bar(items, title="Top edges by peak occupancy")
                    canvas = FigureCanvasTkAgg(fig, master=per_run)
                    canvas.draw()
                    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        except Exception as e:
            ttk.Label(self.dashboard_tab, text=f"Database unavailable: {e}").pack(anchor="w")

        # --- Graph analytics (local, not SQL) ---
        try:
            from smartflow.core.graph_analysis import articulation_points, rank_critical_edges

            g = floorplan.to_networkx()
            analytics_frame = ttk.LabelFrame(self.dashboard_tab, text="Graph analytics (layout structure)", padding=12)
            analytics_frame.pack(fill=tk.BOTH, expand=True)

            arts = articulation_points(g)
            ttk.Label(analytics_frame, text=f"Articulation points: {len(arts)}").pack(anchor="w")
            if arts:
                ttk.Label(analytics_frame, text=", ".join(arts[:12]) + ("..." if len(arts) > 12 else "")).pack(anchor="w")

            ranked = rank_critical_edges(g, edge_metrics=results.edge_metrics, top_k=8)
            if ranked:
                ttk.Label(analytics_frame, text="Critical edges (centrality + congestion):").pack(anchor="w", pady=(8, 2))
                items = [(f"{it.edge[0]}→{it.edge[1]}", float(it.peak_occupancy)) for it in ranked]
                fig = build_top_edges_bar(items, title="Critical edges (peak occupancy)")
                canvas = FigureCanvasTkAgg(fig, master=analytics_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Multi-floor congested edges (per floor + stairs)
            ttk.Label(analytics_frame, text="Most congested edges by floor:").pack(anchor="w", pady=(10, 2))
            mf_notebook = ttk.Notebook(analytics_frame)
            mf_notebook.pack(fill=tk.BOTH, expand=True)

            floors = sorted({int(data.get("floor", 0)) for _, data in g.nodes(data=True)})
            if not floors:
                floors = [0]

            def top_edges_for(filter_fn, title: str):
                items = []
                for u, v, data in g.edges(data=True):
                    if not filter_fn(u, v, data):
                        continue
                    edge_id = str(data.get("id", f"{u}->{v}"))
                    metric = results.edge_metrics.get(edge_id)
                    peak = float(getattr(metric, "peak_occupancy", 0.0)) if metric else 0.0
                    items.append((f"{u}→{v}", peak))
                items.sort(key=lambda x: x[1], reverse=True)
                return items[:8]

            for f in floors:
                tab = ttk.Frame(mf_notebook)
                mf_notebook.add(tab, text=("Ground" if f == 0 else f"Floor {f}"))
                top = top_edges_for(
                    lambda u, v, data, ff=f: int(g.nodes[u].get("floor", 0)) == ff and int(g.nodes[v].get("floor", 0)) == ff,
                    f"Floor {f}",
                )
                fig = build_top_edges_bar(top, title=f"Most congested edges — Floor {f}")
                canvas = FigureCanvasTkAgg(fig, master=tab)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            stairs_tab = ttk.Frame(mf_notebook)
            mf_notebook.add(stairs_tab, text="Stairs")
            stairs_top = top_edges_for(
                lambda u, v, data: bool(data.get("is_stairs", False)) or int(g.nodes[u].get("floor", 0)) != int(g.nodes[v].get("floor", 0)),
                "Stairs",
            )
            fig = build_top_edges_bar(stairs_top, title="Most congested edges — Stairs")
            canvas = FigureCanvasTkAgg(fig, master=stairs_tab)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            ttk.Label(self.dashboard_tab, text=f"Graph analytics unavailable: {e}").pack(anchor="w")

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
            from smartflow.io.persistence import DEFAULT_DB_PATH, save_current_run

            run_id = save_current_run(
                floorplan_path=floorplan_path,
                scenario_config=config or {},
                results=results,
                db_path=DEFAULT_DB_PATH,
            )
            self.controller.state["last_run_id"] = run_id
            messagebox.showinfo("Saved", f"Results saved to database (Run {run_id}).")
            self.save_btn.config(state="disabled")

        except Exception as e:
            messagebox.showerror("Save Error", str(e))
