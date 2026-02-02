"""View for displaying simulation results."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from smartflow.io.exporters import export_csv, export_pdf
from smartflow.io.persistence import save_current_run, DEFAULT_DB_PATH
from smartflow.io import db as dbio
from smartflow.viz.charts import build_active_agents_series, build_top_edges_bar, build_travel_time_histogram
from smartflow.viz.heatmap import build_heatmap_figure, build_layout_figure

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
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="Step 4: Results Analysis", font=("Segoe UI Semibold", 16)).pack(side=tk.LEFT)
        
        # Result Set Selector
        self.result_selector_frame = ttk.Frame(header_frame)
        self.result_selector_frame.pack(side=tk.RIGHT)
        
        ttk.Label(self.result_selector_frame, text="Viewing: ", font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self.result_var = tk.StringVar()
        self.result_combo = ttk.Combobox(self.result_selector_frame, textvariable=self.result_var, state="readonly", width=30)
        self.result_combo.pack(side=tk.LEFT)
        self.result_combo.bind("<<ComboboxSelected>>", self._on_result_changed)
        
        # Save to DB Button
        ttk.Separator(self.result_selector_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.save_db_btn = ttk.Button(self.result_selector_frame, text="Save to History", command=self._save_results) 
        self.save_db_btn.pack(side=tk.LEFT)

        # Notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tabs
        self.heatmap_tab = ttk.Frame(self.notebook)
        self.charts_tab = ttk.Frame(self.notebook)
        self.layout_tab = ttk.Frame(self.notebook)
        self.dashboard_tab = ttk.Frame(self.notebook)
        self.compare_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.heatmap_tab, text="Network Heatmap")
        self.notebook.add(self.charts_tab, text="Performance Charts")
        self.notebook.add(self.layout_tab, text="Layout Inspector")
        self.notebook.add(self.dashboard_tab, text="DB Dashboard")
        self.notebook.add(self.compare_tab, text="Run Comparison (A vs B)")

        self._setup_layout_tab()

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        # Left side: back button
        new_run_btn = ttk.Button(nav_frame, text="< New Run", command=lambda: self.controller.show_frame("ConfigView"))
        new_run_btn.pack(side=tk.LEFT)
        
        # Right side: action buttons (aligned right)
        btn_frame = ttk.Frame(nav_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        self.save_btn = ttk.Button(btn_frame, text="Save to DB", command=self._save_results, state="disabled")
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_csv_btn = ttk.Button(btn_frame, text="Export CSV", command=self._export_csv, state="disabled")
        self.export_csv_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_btn = ttk.Button(btn_frame, text="Export PDF", command=self._export_pdf, state="disabled")
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        compare_btn = ttk.Button(btn_frame, text="Compare Runs", command=lambda: self.controller.show_frame("ComparisonView"))
        compare_btn.pack(side=tk.LEFT, padx=5)

        # Tooltips for accessibility
        try:
            from ..app import create_tooltip
            create_tooltip(self.export_btn, "Export a PDF report with charts and metrics")
            create_tooltip(self.export_csv_btn, "Export raw metrics data to CSV")
            create_tooltip(self.save_btn, "Save this run to the database for later comparison")
            create_tooltip(compare_btn, "Compare two saved simulation runs side-by-side")
        except Exception:
            pass  # Tooltips are optional

    def update_view(self) -> None:
        """Refresh UI with data."""
        # Clean current state
        self.available_results = {}
        
        all_results = self.controller.state.get("all_results")
        single_result = self.controller.state.get("simulation_results")
        
        if all_results:
            self.available_results = dict(all_results)
            # Add Overall if > 1
            if len(all_results) > 1:
               self.available_results["Overall"] = self._aggregate_results(all_results)
        elif single_result:
             self.available_results = {"Simulation": single_result}
        
        if not self.available_results:
             # Clear UI if no results (maybe coming from editor)
             return
             
        # Setup Combo
        keys = list(self.available_results.keys())
        priority = ["start_of_day", "lesson_changeover", "break_time", "Overall"]
        # Sort so priority items come first, others alphabetical
        keys.sort(key=lambda k: priority.index(k) if k in priority else 99)
        
        self.display_map = {k: k.replace("_", " ").title() for k in keys}
        display_values = [self.display_map[k] for k in keys]
        
        self.result_combo['values'] = display_values
        if display_values:
            self.result_combo.current(0)
            self._on_result_changed(None)
            
        # Rebuild Comparison Tab
        for w in self.compare_tab.winfo_children():
            w.destroy()
        self._build_comparison_tab(self.compare_tab)
        
        # Populate Layout Tab (Initial)
        self._rebuild_layout_view(highlight=None)

    def _on_result_changed(self, event):
        display = self.result_var.get()
        # Find key
        key = next((k for k, v in self.display_map.items() if v == display), None)
        if key and key in self.available_results:
            self.current_results_key = key
            # Update 'simulation_results' in state so exporters use the visible one
            self.controller.state["simulation_results"] = self.available_results[key]
            self._render_dashboard(self.available_results[key], self.display_map[key])

    def _aggregate_results(self, results_map):
        from smartflow.core.metrics import MetricsCollector, AgentMetrics, EdgeMetrics, RunSummary
        
        # Create a dummy collector
        agg = MetricsCollector()
        
        # Merge Agents: Rename IDs to avoid collision? Or assume unique?
        # If running same agents in different modes, IDs might collide (e.g. student_0).
        # We should prefix them.
        for mode, collector in results_map.items():
            for agent_id, metric in collector.agent_metrics.items():
                new_id = f"{mode}-{agent_id}"
                agg.record_agent(new_id, metric)

        # Merge Edges: Simply take the maximums?
        # For overall heatmap, we likely want the max occupancy seen across any run.
        all_edge_ids = set()
        for c in results_map.values():
            all_edge_ids.update(c.edge_metrics.keys())
            
        for eid in all_edge_ids:
            # Aggregate logic: Peak of peaks
            peak_occ = 0.0
            throughput = 0
            
            # Simple list merge for occupancy? No, time series would overlap.
            # We can't meaningfully merge time series for "Overall" unless we concatenate.
            # For this MVP, we will just merge Peak Occupancy and Throughput.
            
            for c in results_map.values():
                if eid in c.edge_metrics:
                    m = c.edge_metrics[eid]
                    peak_occ = max(peak_occ, m.peak_occupancy)
                    throughput += m.throughput_count
            
            m = EdgeMetrics(eid)
            m.peak_occupancy = peak_occ
            m.throughput_count = throughput
            agg.edge_metrics[eid] = m
            
        agg.finalize()
        return agg

    def _render_dashboard(self, results, title: str) -> None:
        """Render dashboard for a specific result set."""
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            return

        # Enable buttons based on state
        auto_saved = bool(self.controller.state.get("last_run_auto_saved"))
        # Only allow DB save for real single runs, not aggregate "Overall"
        can_save = (self.current_results_key != "Overall" and not auto_saved)
        self.save_btn.config(state=("normal" if can_save else "disabled"))
        self.export_btn.config(state="normal")
        self.export_csv_btn.config(state="normal")

        # Clear old widgets
        for widget in self.heatmap_tab.winfo_children():
            widget.destroy()
        for widget in self.charts_tab.winfo_children():
            widget.destroy()
        for widget in self.dashboard_tab.winfo_children():
            widget.destroy()
            
        # --- 1. Heatmaps ---
        try:
            graph = floorplan.to_networkx()

            def _parse_floor(value) -> int:
                try:
                    if value is None: return 0
                    if isinstance(value, bool): return int(value)
                    if isinstance(value, (int, float)): return int(value)
                    s = str(value).strip().lower()
                    if s in {"g", "ground", "ground floor"}: return 0
                    cleaned = "".join(ch for ch in s if (ch.isdigit() or ch == "-"))
                    return int(cleaned) if cleaned not in {"", "-"} else 0
                except Exception: return 0

            floors = sorted({_parse_floor(data.get("floor", 0)) for _, data in graph.nodes(data=True)})
            if not floors: floors = [0]

            mode_frame = ttk.Frame(self.heatmap_tab)
            mode_frame.pack(fill=tk.X, pady=(0, 8))
            
            ttk.Label(mode_frame, text="Show Edges:", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
            
            self.heatmap_mode_var = tk.StringVar(value="all")
            
            def refresh_heatmaps():
                self._rebuild_heatmaps(graph, results.edge_metrics, floors, _parse_floor)
            
            ttk.Radiobutton(mode_frame, text="All", variable=self.heatmap_mode_var, value="all", command=refresh_heatmaps).pack(side=tk.LEFT, padx=4)
            ttk.Radiobutton(mode_frame, text="Forward (A->B)", variable=self.heatmap_mode_var, value="forward", command=refresh_heatmaps).pack(side=tk.LEFT, padx=4)
            ttk.Radiobutton(mode_frame, text="Reverse (B->A)", variable=self.heatmap_mode_var, value="reverse", command=refresh_heatmaps).pack(side=tk.LEFT, padx=4)
            
            self._heatmap_graph = graph
            self._heatmap_edge_metrics = results.edge_metrics
            self._heatmap_floors = floors
            self._heatmap_parse_floor = _parse_floor
            
            self.heatmap_container = ttk.Frame(self.heatmap_tab)
            self.heatmap_container.pack(fill=tk.BOTH, expand=True)
            
            self._rebuild_heatmaps(graph, results.edge_metrics, floors, _parse_floor)

        except Exception as e:
            ttk.Label(self.heatmap_tab, text=f"Error loading heatmaps: {e}").pack()
        
        # --- 2. Charts ---
        try:
            # Dynamic Header
            mode_header = ttk.Frame(self.charts_tab) 
            mode_header.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(
                mode_header, 
                text=f"Analytics: {title}",
                font=("Segoe UI Semibold", 12),
                foreground="#2980B9"
            ).pack(anchor="w")
            
            # Summary Statistics
            summary_frame = ttk.Frame(self.charts_tab)
            summary_frame.pack(fill=tk.X, pady=(0, 15))
            
            cards_row = ttk.Frame(summary_frame)
            cards_row.pack(fill=tk.X)
            
            def stat_card(parent, label: str, value: str, col: int) -> None:
                card = ttk.Frame(parent, padding=12)
                card.grid(row=0, column=col, padx=8, pady=4, sticky="nsew")
                ttk.Label(card, text=value, font=("Segoe UI Semibold", 16)).pack(anchor="center")
                ttk.Label(card, text=label, font=("Segoe UI", 9)).pack(anchor="center", pady=(4, 0))
            
            for i in range(5): cards_row.columnconfigure(i, weight=1)

            summary = results.summary
            agent_count = len(results.agent_metrics)
            mean_time = f"{summary.mean_travel_time_s:.1f}s" if summary.mean_travel_time_s else "—"
            p90_time = f"{summary.p90_travel_time_s:.1f}s" if summary.p90_travel_time_s else "—"
            
            delays = [m.delay_s for m in results.agent_metrics.values()]
            total_delay = f"{sum(delays):.0f}s" if delays else "0s"
            
            late_count = sum(1 for m in results.agent_metrics.values() if m.is_late)
            late_pct = f"{(late_count/agent_count)*100:.1f}%" if agent_count > 0 else "0%"
            
            stat_card(cards_row, "Agents", str(agent_count), 0)
            stat_card(cards_row, "Mean Travel", mean_time, 1)
            stat_card(cards_row, "P90 Travel", p90_time, 2)
            stat_card(cards_row, "Total Delay", total_delay, 3)
            stat_card(cards_row, "Late Agents", f"{late_count} ({late_pct})", 4)
            
            chart_frame = ttk.Frame(self.charts_tab)
            chart_frame.pack(fill=tk.BOTH, expand=True)
            
            if self.current_results_key == "Overall":
                ttk.Label(chart_frame, text="Time series charts not available for aggregated view.", padding=20).pack()
            else:
                fig_hist = build_travel_time_histogram(results.agent_metrics)
                canvas_hist = FigureCanvasTkAgg(fig_hist, master=chart_frame)
                canvas_hist.draw()
                canvas_hist.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Active Agents Series (Pass tick_seconds=0.05)
                # Need to check total ticks or get it from metrics
                total_ticks = 0
                if results.edge_metrics:
                    total_ticks = len(next(iter(results.edge_metrics.values())).occupancy_over_time)
                
                fig_series = build_active_agents_series(results.edge_metrics, total_ticks, tick_seconds=0.05)
                canvas_series = FigureCanvasTkAgg(fig_series, master=chart_frame)
                canvas_series.draw()
                canvas_series.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        except Exception as e:
            print(f"Error drawing charts: {e}")
            ttk.Label(self.charts_tab, text=f"Error: {e}").pack()

        # --- 3. Dashboard ---
        # (Re-use existing _build_dashboard logic or simplify it)
        try:
            if self.current_results_key != "Overall":
                self._build_dashboard(results, floorplan)
            else:
                 ttk.Label(self.dashboard_tab, text="DB Dashboard specific to single runs.").pack(pady=20)
        except Exception as e:
             pass

        # 3. DB dashboard + analytics
        try:
            self._build_dashboard(results, floorplan)
        except Exception as e:
            ttk.Label(self.dashboard_tab, text=f"Error loading dashboard: {e}").pack(anchor="w")


    def _build_dashboard(self, results, floorplan) -> None:
        """Render a simple dashboard from SQL aggregates + graph analytics."""

        header = ttk.Label(self.dashboard_tab, text="Saved Runs Dashboard", font=("Segoe UI Semibold", 12))
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
            kv_row(stats_frame, "Avg delay (s)", round(float(stats.get("avg_delay_s") or 0.0), 2))
            kv_row(stats_frame, "Total late (all runs)", int(stats.get("total_late_count") or 0))
            kv_row(stats_frame, "Avg % late", f"{round(float(stats.get('avg_percent_late') or 0.0), 1)}%")

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

            def _parse_floor(value) -> int:
                try:
                    if value is None:
                        return 0
                    if isinstance(value, bool):
                        return int(value)
                    if isinstance(value, (int, float)):
                        return int(value)
                    s = str(value).strip().lower()
                    if s in {"g", "ground", "ground floor"}:
                        return 0
                    cleaned = "".join(ch for ch in s if (ch.isdigit() or ch == "-"))
                    return int(cleaned) if cleaned not in {"", "-"} else 0
                except Exception:
                    return 0

            floors = sorted({_parse_floor(data.get("floor", 0)) for _, data in g.nodes(data=True)})
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
                return items[:50] # Allow scrolling 50 items

            for f in floors:
                tab = ttk.Frame(mf_notebook)
                mf_notebook.add(tab, text=("Ground" if f == 0 else f"Floor {f}"))
                top = top_edges_for(
                    lambda u, v, data, ff=f: _parse_floor(g.nodes[u].get("floor", 0)) == ff and _parse_floor(g.nodes[v].get("floor", 0)) == ff,
                    f"Floor {f}",
                )
                
                # Scroll wrapper
                container = ttk.Frame(tab)
                container.pack(fill=tk.BOTH, expand=True)
                
                sub_canvas = tk.Canvas(container)
                scrollbar = ttk.Scrollbar(container, orient="vertical", command=sub_canvas.yview)
                scrollable_frame = ttk.Frame(sub_canvas)
                
                scrollable_frame.bind(
                    "<Configure>",
                    lambda e, c=sub_canvas: c.configure(scrollregion=c.bbox("all"))
                )

                sub_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                sub_canvas.configure(yscrollcommand=scrollbar.set)
                
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                sub_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Dynamic height based on items
                dynamic_height = max(4, len(top) * 0.4) 
                
                from smartflow.viz.charts import Figure
                # Clone logic of build_top_edges_bar but with dynamic size
                fig = Figure(figsize=(6, dynamic_height), dpi=100)
                ax = fig.add_subplot(111)

                if not top:
                    ax.text(0.5, 0.5, "No Data", ha="center", va="center")
                    ax.set_axis_off()
                else:
                    labels = [e[0] for e in top]
                    values = [float(e[1]) for e in top]

                    ax.barh(range(len(values)), values, color="#e67e22")
                    ax.set_yticks(range(len(labels)))
                    ax.set_yticklabels(labels)
                    ax.invert_yaxis()
                    ax.set_xlabel("Peak occupancy (people)")
                    ax.set_title(f"Most congested edges — Floor {f}")
                    ax.grid(True, axis="x", linestyle="--", alpha=0.4)
                    fig.subplots_adjust(left=0.35, bottom=0.15/dynamic_height*4, right=0.95, top=1.0 - (0.4/dynamic_height))

                canvas_w = FigureCanvasTkAgg(fig, master=scrollable_frame)
                canvas_w.draw()
                canvas_w.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            stairs_tab = ttk.Frame(mf_notebook)
            mf_notebook.add(stairs_tab, text="Stairs")
            stairs_top = top_edges_for(
                lambda u, v, data: bool(data.get("is_stairs", False)) or _parse_floor(g.nodes[u].get("floor", 0)) != _parse_floor(g.nodes[v].get("floor", 0)),
                "Stairs",
            )
            # Standard Fixed size for stairs or scrollable too? Let's make it standard for now or scrollable if many
            fig = build_top_edges_bar(stairs_top[:10], title="Most congested edges — Stairs")
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
                messagebox.showerror("Export Error", str(e))

    def _build_comparison_tab(self, parent: ttk.Frame) -> None:
        """Create comparison widgets inside the new tab."""
        
        # Controls Frame
        ctrl_frame = ttk.Frame(parent, padding=10)
        ctrl_frame.pack(fill=tk.X)
        
        ttk.Label(ctrl_frame, text="Baseline (A):").pack(side=tk.LEFT)
        self.cmb_run_a = ttk.Combobox(ctrl_frame, width=30, state="readonly")
        self.cmb_run_a.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(ctrl_frame, text="Target (B):").pack(side=tk.LEFT)
        self.cmb_run_b = ttk.Combobox(ctrl_frame, width=30, state="readonly")
        self.cmb_run_b.pack(side=tk.LEFT, padx=5)
        
        refresh_btn = ttk.Button(ctrl_frame, text="Refresh", command=self._refresh_run_choices)
        refresh_btn.pack(side=tk.RIGHT, padx=5)
        
        cmp_btn = ttk.Button(ctrl_frame, text="Compare Runs", command=self._do_compare_runs)
        cmp_btn.pack(side=tk.RIGHT)
        
        # Results Table
        cols = ("metric", "val_a", "val_b", "diff", "pct")
        self.cmp_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.cmp_tree.heading("metric", text="Metric")
        self.cmp_tree.heading("val_a", text="Run A Value")
        self.cmp_tree.heading("val_b", text="Run B Value")
        self.cmp_tree.heading("diff", text="Difference")
        self.cmp_tree.heading("pct", text="% Change")
        
        self.cmp_tree.column("metric", width=200)
        self.cmp_tree.column("val_a", width=100, anchor="center")
        self.cmp_tree.column("val_b", width=100, anchor="center")
        self.cmp_tree.column("diff", width=100, anchor="center")
        self.cmp_tree.column("pct", width=100, anchor="center")
        
        self.cmp_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Populate dropdowns
        self._refresh_run_choices()

    def _refresh_run_choices(self) -> None:
        """Load past runs from SQL DB."""
        try:
            self._run_choices = {} # Label -> ID map
            
            import sqlite3
            from smartflow.io.persistence import DEFAULT_DB_PATH
            path = Path(DEFAULT_DB_PATH)
            if not path.exists():
                return
                
            with sqlite3.connect(path) as conn:
                # Fetch ID, Scenario Name, timestamp
                cursor = conn.execute("""
                    SELECT r.id, s.name, r.started_at, r.mean_travel_s
                    FROM runs r
                    JOIN scenarios s ON r.scenario_id = s.id
                    ORDER BY r.id DESC
                    LIMIT 50
                """)
                rows = cursor.fetchall()
            
            labels = []
            for r in rows:
                rid, rname, rtime, rmean = r
                label = f"#{rid}: {rname} ({str(rtime)[:16]})"
                labels.append(label)
                self._run_choices[label] = rid
            
            self.cmb_run_a['values'] = labels
            self.cmb_run_b['values'] = labels
            
            if len(labels) > 0: self.cmb_run_a.current(0)
            if len(labels) > 1: self.cmb_run_b.current(1)
            
        except Exception as e:
            print(f"Error loading runs: {e}")

    def _do_compare_runs(self) -> None:
        """Fetch data for selected A/B and display diff."""
        from smartflow.io import db as dbio
        from smartflow.io.persistence import DEFAULT_DB_PATH
        
        stop_needed = False
        lbl_a = self.cmb_run_a.get()
        lbl_b = self.cmb_run_b.get()
        
        if not lbl_a or not lbl_b:
            return
            
        id_a = self._run_choices.get(lbl_a)
        id_b = self._run_choices.get(lbl_b)
        
        if id_a is None or id_b is None:
            return
            
        try:
            data_a, data_b = dbio.get_comparison_data(Path(DEFAULT_DB_PATH), id_a, id_b)
            if not data_a or not data_b:
                messagebox.showerror("Error", "Could not load run data.")
                return
                
            # Clear Table
            for i in self.cmp_tree.get_children():
                self.cmp_tree.delete(i)
                
            # Metrics to show
            # (Label, Key, HigherIsBetter?)
            metrics_list = [
                ("Mean Travel Time (s)", "mean_travel_s", False),
                ("Max Edge Density (p/m2)", "max_edge_density", False),
                ("Percent Late (%)", "percent_late", False),
                ("Start Late (Delay)", "p50_travel_s", False) # or any other field
            ]

            # Efficiency Calc Helper
            def calc_score(d):
                t = float(d.get("mean_travel_s") or 60)
                l = float(d.get("percent_late") or 0)
                c = float(d.get("max_edge_density") or 0)
                # Formula: Base 100 - (Travel > 60) - (Late * 1) - (Congestion * 5)
                score = 100.0 - max(0, t - 60)*0.2 - (l * 1.0) - (c * 5.0)
                return max(0.0, score)
                
            score_a = calc_score(data_a)
            score_b = calc_score(data_b)

            # 1. Add metrics rows
            for label, key, higher_better in metrics_list:
                val_a = float(data_a.get(key) or 0)
                val_b = float(data_b.get(key) or 0)
                
                diff = val_b - val_a
                pct = 0.0
                if val_a != 0: pct = (diff/val_a) * 100
                
                self.cmp_tree.insert("", "end", values=(
                    label,
                    f"{val_a:.2f}",
                    f"{val_b:.2f}",
                    f"{diff:+.2f}",
                    f"{pct:+.1f}%"
                ))

            self.cmp_tree.insert("", "end", values=("", "", "", "", ""))
            
            # 2. Add Efficiency Score
            diff_score = score_b - score_a
            pct_score = 0.0
            if score_a != 0: pct_score = (diff_score/score_a)*100
            
            self.cmp_tree.insert("", "end", values=(
                "OVERALL EFFICIENCY SCORE",
                f"{score_a:.1f}",
                f"{score_b:.1f}",
                f"{diff_score:+.1f}",
                f"{pct_score:+.1f}%"
            ), tags=("score",))
            
            self.cmp_tree.tag_configure("score", background="#e3f2fd", font=("Segoe UI", 9, "bold"))
            
        except Exception as e:
            messagebox.showerror("Compare Error", str(e))
    def _save_results(self) -> None:
        """Save the current run to the database."""
        results = self.controller.state.get("simulation_results")
        floorplan_path_str = self.controller.state.get("floorplan_path")
        config = self.controller.state.get("scenario_config")
        
        if not results or not floorplan_path_str:
            return
            
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH, save_current_run
            
            run_id = save_current_run(
                floorplan_path=Path(floorplan_path_str),
                scenario_config=config or {},
                results=results,
                db_path=DEFAULT_DB_PATH,
            )
            self.controller.state["last_run_id"] = run_id
            messagebox.showinfo("Saved", f"Results saved to database (Run {run_id}).")
            self.save_btn.config(state="disabled")
            if hasattr(self, "save_db_btn"):
                self.save_db_btn.config(state="disabled", text="Saved")

        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _export_csv(self) -> None:
        """Export metrics to CSV file."""
        results = self.controller.state.get("simulation_results")
        if not results:
            return

        file_path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )

        if file_path:
            try:
                # Build rows from agent metrics
                rows = []
                for agent_id, m in results.agent_metrics.items():
                    rows.append({
                        "agent_id": agent_id,
                        "travel_time_s": m.travel_time_s,
                        "delay_s": m.delay_s,
                        "is_late": m.is_late,
                        "scheduled_arrival_s": m.scheduled_arrival_s,
                        "actual_arrival_s": m.actual_arrival_s,
                    })
                export_csv(Path(file_path), rows)
                messagebox.showinfo("Export Success", f"CSV saved to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export CSV:\n{str(e)}")

    def _rebuild_heatmaps(self, graph, edge_metrics, floors, _parse_floor) -> None:
        """Rebuild heatmap visualizations based on current direction filter mode."""
        # Clear existing
        for widget in self.heatmap_container.winfo_children():
            widget.destroy()
        
        mode = self.heatmap_mode_var.get()
        
        # Set title suffix based on mode
        if mode == "forward":
            title_suffix = " (Forward A→B)"
        elif mode == "reverse":
            title_suffix = " (Reverse B→A)"
        else:
            title_suffix = ""
        
        heatmap_notebook = ttk.Notebook(self.heatmap_container)
        heatmap_notebook.pack(fill=tk.BOTH, expand=True)

        # All floors
        all_tab = ttk.Frame(heatmap_notebook)
        heatmap_notebook.add(all_tab, text="All Floors")
        fig_all = build_heatmap_figure(
            graph, edge_metrics,
            title=f"Congestion Heatmap{title_suffix}",
            direction_filter=mode
        )
        canvas_all = FigureCanvasTkAgg(fig_all, master=all_tab)
        canvas_all.draw()
        canvas_all.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Per-floor
        for f in floors:
            tab = ttk.Frame(heatmap_notebook)
            heatmap_notebook.add(tab, text=("Ground" if f == 0 else f"Floor {f}"))
            fig_floor = build_heatmap_figure(
                graph,
                edge_metrics,
                title=(f"Congestion — Floor {f}{title_suffix}"),
                floor=int(f),
                direction_filter=mode,
            )
            canvas_floor = FigureCanvasTkAgg(fig_floor, master=tab)
            canvas_floor.draw()
            canvas_floor.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _save_to_db(self) -> None:
        """Save currently viewed results to the SQLite database."""
        if not self.visible_results:
            return
            
        try:
            # Use persistence layer to save
            floorplan_path_str = self.controller.state.get("floorplan_path")
            if not floorplan_path_str:
                messagebox.showerror("Error", "Cannot save: No floorplan path found.")
                return
                
            from smartflow.io.persistence import save_current_run
            
            run_id = save_current_run(
                floorplan_path=Path(floorplan_path_str),
                scenario_config=self.controller.state.get("scenario_config", {}),
                results=self.visible_results
            )
            
            messagebox.showinfo("Success", f"Run saved to database with ID: {run_id}")
            self.save_db_btn.config(state="disabled", text="Saved")
            try:
                self._update_dashboard()
            except Exception:
                pass # Dashboard update is optional
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to save run: {e}")

    def _setup_layout_tab(self) -> None:
        """Build the UI for the Layout Inspector tab."""
        # Search Bar
        search_frame = ttk.Frame(self.layout_tab, padding=10)
        search_frame.pack(fill=tk.X)
        
        ttk.Label(search_frame, text="Search Node/Edge (e.g. J66, J12->J11):").pack(side=tk.LEFT)
        self.layout_search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.layout_search_var, width=30)
        entry.pack(side=tk.LEFT, padx=5)
        entry.bind("<Return>", lambda e: self._perform_layout_search())
        
        btn = ttk.Button(search_frame, text="Search", command=self._perform_layout_search)
        btn.pack(side=tk.LEFT)
        
        self.search_status_lbl = ttk.Label(search_frame, text="", foreground="red")
        self.search_status_lbl.pack(side=tk.LEFT, padx=10)
        
        # Scrollable Container
        container = ttk.Frame(self.layout_tab)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        self.layout_scroll_frame = ttk.Frame(canvas)
        self.layout_canvas_window = canvas.create_window((0, 0), window=self.layout_scroll_frame, anchor="nw")
        
        # Update scroll region when frame resizes
        self.layout_scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.layout_main_canvas = canvas 

    def _perform_layout_search(self) -> None:
        """Highlight a node or edge in the layout inspector."""
        query = self.layout_search_var.get().strip()
        if not query:
            self._rebuild_layout_view(highlight=None)
            self.search_status_lbl.config(text="")
            return
            
        floorplan = self.controller.state.get("floorplan")
        if not floorplan: return
        
        graph = floorplan.graph
        
        found = False
        target_floor = None
        
        # Check Node
        if query in graph.nodes:
            found = True
            d = graph.nodes[query]
            try: 
                s = str(d.get("floor", 0)).lower()
                target_floor = 0 if s in ('g','ground') else int(''.join(c for c in s if c.isdigit()) or 0)
            except: 
                target_floor = 0
        
        # Check Edge
        if not found:
            # Handle J66->J70 or J66-J70
            parts = query.replace("->", "-").split("-")
            if len(parts) == 2:
                u, v = parts[0].strip(), parts[1].strip()
                if graph.has_edge(u, v) or graph.has_edge(v, u):
                    found = True
                    # Assume floor of 'u'
                    if u in graph.nodes:
                         d = graph.nodes[u]
                         try: 
                            s = str(d.get("floor", 0)).lower()
                            target_floor = 0 if s in ('g','ground') else int(''.join(c for c in s if c.isdigit()) or 0)
                         except: 
                            target_floor = 0

        if found:
            self.search_status_lbl.config(text="Found!", foreground="green")
            self._rebuild_layout_view(highlight=query)
            # Schedule scroll
            self.after(200, lambda: self._scroll_to_floor(target_floor))
        else:
            self.search_status_lbl.config(text="Not found", foreground="red")

    def _rebuild_layout_view(self, highlight=None) -> None:
        """Draw all floors stacked vertically."""
        if not hasattr(self, 'layout_scroll_frame'): return
        
        # Clear existing
        for c in self.layout_scroll_frame.winfo_children(): c.destroy()
        
        floorplan = self.controller.state.get("floorplan")
        if not floorplan: return
        
        def _parse_f(val):
             try: 
                s = str(val).lower()
                if s in ('g','ground'): return 0
                return int(''.join(c for c in s if c.isdigit()) or 0)
             except: return 0
        
        floors = sorted(list({_parse_f(d.get("floor",0)) for n,d in floorplan.graph.nodes(data=True)}))
        
        for f in floors:
            f_frame = ttk.Frame(self.layout_scroll_frame, padding=10, relief="solid", borderwidth=1)
            f_frame.pack(fill=tk.X, expand=True, pady=10, padx=10)
            
            lbl = ttk.Label(f_frame, text=f"Floor {f}", font=("Segoe UI", 12, "bold"))
            lbl.pack(anchor="w")
            
            # Using our new viz function
            fig = build_layout_figure(floorplan.graph, f, highlight_item=highlight, figsize=(10, 6))
            
            canvas = FigureCanvasTkAgg(fig, master=f_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # Tag for scrolling
            f_frame.floor_num = f

    def _scroll_to_floor(self, floor_num):
        if not hasattr(self, 'layout_scroll_frame'): return
        
        target_y = 0
        found = False
        
        for widget in self.layout_scroll_frame.winfo_children():
            if getattr(widget, 'floor_num', None) == floor_num:
                target_y = widget.winfo_y()
                found = True
                break
        
        if found:
            h = self.layout_scroll_frame.winfo_height()
            if h > 50: # avoid div/0
                self.layout_main_canvas.yview_moveto(target_y / h)

