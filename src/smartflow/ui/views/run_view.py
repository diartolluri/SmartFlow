"""View for running simulations."""

from __future__ import annotations

import random
import math
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, List, Dict, Any, Tuple

from smartflow.core.agents import AgentProfile, AgentScheduleEntry
from smartflow.core.metrics import AgentMetrics
from smartflow.core.model import SimulationConfig, SmartFlowModel
from smartflow.core.scenario_loader import (
    create_agents_from_scenario,
    generate_simple_test_agents,
    generate_break_time_agents,
    generate_start_of_day_agents,
    generate_lesson_changeover_agents
)

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class RunView(ttk.Frame):
    """Frame providing controls to run or stop simulations."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        self.model: SmartFlowModel | None = None
        self.is_running = False
        
        # Visualisation state
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.node_coords: Dict[str, Tuple[float, float]] = {}
        self.agent_offsets: Dict[str, float] = {} # Store lateral offset for each agent
        self.agent_visual_pos: Dict[str, Tuple[float, float]] = {}  # Smoothed on-screen position
        self.agent_canvas_ids: Dict[int, int] = {}  # Persistent canvas IDs for agents to avoid create/delete churn

        # Playback + lesson changeover configuration
        self.playback_mult_var = tk.DoubleVar(value=1.0)
        self.playback_label_var = tk.StringVar(value="1.0×")
        self.changeover_minutes_var = tk.IntVar(value=5)

        # Simulation mode: start_of_day, lesson_changeover, break_time
        self.sim_mode_var = tk.StringVar(value="lesson_changeover")

        # Fast-run: execute multiple model ticks per UI frame (metrics stay identical)
        self.skip_animation_var = tk.BooleanVar(value=False)
        
        self.current_period_index = 0
        self.scenario_periods = []
        
        # Threading support for responsive UI
        self.model_lock = threading.Lock()
        self._active_worker_thread: threading.Thread | None = None

        # Track default start button behaviour so we can temporarily repurpose it
        # for "Run next period" when sequencing scenario periods.
        self._start_button_default_text = "Start Simulation"
        self._stop_event = threading.Event()
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialise UI components."""
        # Header
        header = ttk.Label(self, text="Step 3: Run Simulation", font=("Segoe UI Semibold", 16))
        header.pack(pady=(0, 10))

        # Main content area (Split into Left: Controls/Status, Right: Visualisation)
        content = ttk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True)
        
        left_panel = ttk.Frame(content, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        right_panel = ttk.Frame(content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Left Panel ---
        
        # Status Frame
        status_frame = ttk.LabelFrame(left_panel, text="Status", padding=16)
        status_frame.pack(fill=tk.X, pady=10)

        self.status_var = tk.StringVar(value="Ready to start.")
        ttk.Label(status_frame, textvariable=self.status_var, wraplength=250).pack(anchor="w")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))

        # Simulation Mode Selection (Checkboxes for multi-mode)
        mode_frame = ttk.LabelFrame(left_panel, text="Simulation Mode(s)", padding=10)
        mode_frame.pack(fill=tk.X, pady=10)
        
        self.mode_vars = {
            "start_of_day": tk.BooleanVar(value=False),
            "lesson_changeover": tk.BooleanVar(value=True),
            "break_time": tk.BooleanVar(value=False),
        }
        
        self.mode_labels = {
            "start_of_day": "Start of Day",
            "lesson_changeover": "Lesson Changeover",
            "break_time": "Break Time",
        }
        
        # Order matters for the checklist
        for key in ["start_of_day", "lesson_changeover", "break_time"]:
            ttk.Checkbutton(
                mode_frame,
                text=self.mode_labels[key],
                variable=self.mode_vars[key],
            ).pack(anchor="w")

        # Controls
        control_frame = ttk.Frame(left_panel)
        control_frame.pack(pady=20)

        self.start_btn = ttk.Button(control_frame, text="Start Selection", command=self._start_sequence)
        self.start_btn.pack(fill=tk.X, pady=5)

        self.stop_btn = ttk.Button(control_frame, text="Pause", command=self._stop_simulation, state="disabled")
        self.stop_btn.pack(fill=tk.X, pady=5)

        # Add tooltips
        try:
            from ..app import create_tooltip
            create_tooltip(self.start_btn, "Start the simulation (or press Space to pause/resume)")
            create_tooltip(self.stop_btn, "Pause the simulation (Space key also works)")
        except Exception:
            pass

        # Timer settings
        changeover_frame = ttk.LabelFrame(left_panel, text="Timer Settings", padding=10)
        changeover_frame.pack(fill=tk.X, pady=10)

        ttk.Label(changeover_frame, text="Duration (minutes):").pack(anchor="w")
        ttk.Spinbox(
            changeover_frame,
            from_=1,
            to=20,
            textvariable=self.changeover_minutes_var,
            width=6,
        ).pack(anchor="w", pady=(2, 0))

        # Display options
        display_frame = ttk.LabelFrame(left_panel, text="Display", padding=10)
        display_frame.pack(fill=tk.X, pady=10)

        self.show_grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            display_frame,
            text="Show 5m grid",
            variable=self.show_grid_var,
            command=self._setup_visualization,
        ).pack(anchor="w")

        # Floor Control
        self.floor_frame = ttk.LabelFrame(left_panel, text="Floor View", padding=10)
        self.floor_frame.pack(fill=tk.X, pady=10)
        
        self.floor_var = tk.IntVar(value=0)
        # Buttons will be populated in update_view()

        # Room key (per floor)
        self.key_frame = ttk.LabelFrame(left_panel, text="Room Key", padding=10)
        self.key_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Scrollable container so the full key is always reachable.
        key_outer = ttk.Frame(self.key_frame)
        key_outer.pack(fill=tk.BOTH, expand=True)

        self.key_canvas = tk.Canvas(key_outer, highlightthickness=0)
        key_scroll = ttk.Scrollbar(key_outer, orient=tk.VERTICAL, command=self.key_canvas.yview)
        self.key_canvas.configure(yscrollcommand=key_scroll.set)

        self.key_canvas.grid(row=0, column=0, sticky="nsew")
        key_scroll.grid(row=0, column=1, sticky="ns")
        key_outer.grid_rowconfigure(0, weight=1)
        key_outer.grid_columnconfigure(0, weight=1)

        self.key_inner = ttk.Frame(self.key_canvas)
        key_window = self.key_canvas.create_window((0, 0), window=self.key_inner, anchor="nw")

        def _key_configure(_e: tk.Event) -> None:
            try:
                self.key_canvas.configure(scrollregion=self.key_canvas.bbox("all"))
                self.key_canvas.itemconfigure(key_window, width=self.key_canvas.winfo_width())
            except Exception:
                pass

        self.key_inner.bind("<Configure>", _key_configure)
        self.key_canvas.bind("<Configure>", _key_configure)

        self.legend_frame = ttk.Frame(self.key_inner)
        self.legend_frame.pack(fill=tk.X)

        ttk.Label(self.legend_frame, text="Colour Key", font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.legend_items_frame = ttk.Frame(self.legend_frame)
        self.legend_items_frame.pack(fill=tk.X, pady=(4, 8))

        # --- Right Panel (Visualisation) ---
        
        viz_frame = ttk.LabelFrame(right_panel, text="Live View", padding=5)
        viz_frame.pack(fill=tk.BOTH, expand=True)

        viz_inner = ttk.Frame(viz_frame)
        viz_inner.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(viz_inner, bg="white", highlightthickness=0)
        h_scroll = ttk.Scrollbar(viz_inner, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(viz_inner, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        viz_inner.grid_rowconfigure(0, weight=1)
        viz_inner.grid_columnconfigure(0, weight=1)

        # Panning (middle mouse) + wheel scrolling (Shift = horizontal)
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))

        def _on_wheel(e: tk.Event) -> None:
            try:
                delta = int(getattr(e, "delta", 0))
            except Exception:
                delta = 0
            if delta == 0:
                return
            steps = -1 if delta > 0 else 1
            if bool(getattr(e, "state", 0) & 0x0001):
                self.canvas.xview_scroll(steps, "units")
            else:
                self.canvas.yview_scroll(steps, "units")

        self.canvas.bind("<MouseWheel>", _on_wheel)

        # Playback control at the bottom (0.5x .. 4x)
        playback_frame = ttk.LabelFrame(right_panel, text="Playback Speed", padding=8)
        playback_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(6, 0))

        ttk.Label(playback_frame, text="0.5×").pack(side=tk.LEFT)
        ttk.Scale(
            playback_frame,
            from_=0.5,
            to=4.0,
            variable=self.playback_mult_var,
            orient=tk.HORIZONTAL,
            command=lambda v: self.playback_label_var.set(f"{float(v):.1f}×"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Label(playback_frame, textvariable=self.playback_label_var, width=5, anchor="e").pack(side=tk.LEFT)
        ttk.Label(playback_frame, text="4.0×").pack(side=tk.LEFT)

        ttk.Separator(playback_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Checkbutton(
            playback_frame,
            text="Skip animation",
            variable=self.skip_animation_var,
        ).pack(side=tk.LEFT)

        # Loading indicator (hidden by default)
        self.loading_label = ttk.Label(playback_frame, text="⏳ Computing...", foreground="#2980B9")
        # Will be shown/hidden during fast-run

        # Always-visible Next/Results control (bottom nav can be off-screen on small windows)
        self.playback_next_btn = ttk.Button(playback_frame, text="Next", command=self._go_next, state="disabled")
        self.playback_next_btn.pack(side=tk.RIGHT, padx=(8, 0))
        
        # Navigation (Bottom)
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back", command=lambda: self.controller.show_frame("ConfigView"))
        back_btn.pack(side=tk.LEFT)
        
        self.next_btn = ttk.Button(nav_frame, text="Next: Results >", command=self._go_next, state="disabled")
        self.next_btn.pack(side=tk.RIGHT)

    def update_view(self) -> None:
        """Refresh UI based on current state."""
        # Populate floor selector
        for widget in self.floor_frame.winfo_children():
            widget.destroy()
            
        floorplan = self.controller.state.get("floorplan")
        if floorplan:
            floors = sorted({n.floor for n in floorplan.nodes})
            if not floors:
                floors = [0]
                
            for f in floors:
                text = f"Ground Floor ({f})" if f == 0 else f"Floor {f}"
                ttk.Radiobutton(
                    self.floor_frame, 
                    text=text, 
                    variable=self.floor_var, 
                    value=f, 
                    command=self._setup_visualization
                ).pack(anchor="w")
                
            # Ensure current selection is valid
            if self.floor_var.get() not in floors:
                self.floor_var.set(floors[0])
                
        self._setup_visualization()

    def _setup_visualization(self) -> None:
        """Prepare canvas scaling and draw static floorplan."""
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            return
            
        self.canvas.delete("all")
        self.node_coords.clear()
        self.agent_canvas_ids.clear()
        
        # Calculate bounds
        xs = [n.position[0] for n in floorplan.nodes]
        ys = [n.position[1] for n in floorplan.nodes]
        
        if not xs or not ys:
            return
            
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        width_m = max_x - min_x
        height_m = max_y - min_y
        
        # Add padding
        padding_m = 5.0
        min_x -= padding_m
        min_y -= padding_m
        width_m += 2 * padding_m
        height_m += 2 * padding_m
        
        # Canvas dimensions
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600

        # Scale policy: keep small layouts readable, allow large layouts to be panned.
        fit_scale_x = cw / width_m if width_m > 0 else 1.0
        fit_scale_y = ch / height_m if height_m > 0 else 1.0
        fit_scale = min(fit_scale_x, fit_scale_y)
        min_px_per_m = 10.0
        self.scale = max(min_px_per_m, fit_scale)

        # Use a world coordinate system with a scrollregion.
        padding_px = 40.0
        world_w_px = width_m * self.scale + padding_px * 2
        world_h_px = height_m * self.scale + padding_px * 2
        self.offset_x = 0.0
        self.offset_y = 0.0

        def to_screen(x: float, y: float) -> Tuple[float, float]:
            sx = (x - min_x) * self.scale + padding_px
            sy = (max_y - y) * self.scale + padding_px
            return (sx, sy)

        # Ensure scrollbars can reach the full map in both directions.
        self.canvas.configure(scrollregion=(0, 0, max(world_w_px, cw), max(world_h_px, ch)))

        # Draw 5m grid (behind everything else)
        if getattr(self, "show_grid_var", None) is not None and bool(self.show_grid_var.get()):
            grid_m = 5.0
            x0 = min_x
            x1 = min_x + width_m
            y0 = min_y
            y1 = min_y + height_m

            start_x = math.floor(x0 / grid_m) * grid_m
            end_x = math.ceil(x1 / grid_m) * grid_m
            start_y = math.floor(y0 / grid_m) * grid_m
            end_y = math.ceil(y1 / grid_m) * grid_m

            # Subtle grid style
            grid_color = "#f0f0f0"
            grid_dash = (2, 6)

            x = start_x
            while x <= end_x + 1e-9:
                sx0, sy0 = to_screen(x, y0)
                sx1, sy1 = to_screen(x, y1)
                self.canvas.create_line(sx0, sy0, sx1, sy1, fill=grid_color, dash=grid_dash, tags=("grid",))
                x += grid_m

            y = start_y
            while y <= end_y + 1e-9:
                sx0, sy0 = to_screen(x0, y)
                sx1, sy1 = to_screen(x1, y)
                self.canvas.create_line(sx0, sy0, sx1, sy1, fill=grid_color, dash=grid_dash, tags=("grid",))
                y += grid_m

            # No on-canvas labels (use colour key instead)

        # Store node screen coords
        current_floor = self.floor_var.get()
        
        for node in floorplan.nodes:
            if node.floor == current_floor:
                self.node_coords[node.node_id] = to_screen(node.position[0], node.position[1])
            
        # Draw Edges (Corridors)
        for edge in floorplan.edges:
            u = edge.source
            v = edge.target
            
            # Only draw if both nodes are on current floor
            # Or if it's a stair connecting to current floor (maybe draw as dashed?)
            if u in self.node_coords and v in self.node_coords:
                x1, y1 = self.node_coords[u]
                x2, y2 = self.node_coords[v]
                # Draw thick grey line for corridor
                width = max(2, edge.width_m * self.scale)
                
                # Dashed for stairs
                dash = (4, 4) if edge.is_stairs else None
                color = "#e0e0e0" if not edge.is_stairs else "#ffcc00"
                
                self.canvas.create_line(x1, y1, x2, y2, width=width, fill=color, capstyle=tk.ROUND, dash=dash)
                
        # Draw Nodes
        for node in floorplan.nodes:
            if node.node_id not in self.node_coords:
                continue
                
            x, y = self.node_coords[node.node_id]
            r = 3 # Radius

            is_entrance = bool(getattr(node, "metadata", None) and node.metadata.get("is_entrance", False))

            # Room subject (for key + colour)
            try:
                subject = str((node.metadata or {}).get("subject", "other")).lower()
            except Exception:
                subject = "other"

            subject_colors = {
                "maths": "#2E86AB",
                "english": "#8E44AD",
                "science": "#27AE60",
                "humanities": "#D35400",
                "computer science": "#2C3E50",
                "technology": "#16A085",
                "art": "#C0392B",
                "library": "#7F8C8D",
                "sports hall": "#2980B9",
                "canteen": "#FF9800",
                "seating_area": "#4CAF50",
                "other": "#4a90e2",
            }
            
            # Colour coding
            if node.kind == "room":
                color = subject_colors.get(subject, subject_colors["other"])
            elif node.kind == "canteen":
                color = "#FF9800"  # Orange for canteen
            elif node.kind == "seating_area":
                color = "#4CAF50"  # Green for seating area
            elif node.kind == "toilet":
                color = "#e24a90" # Pink
            elif node.kind == "stairs":
                color = "#ffcc00" # Yellow
            elif node.kind == "entry" or is_entrance:
                color = "#50c878" # Emerald Green
                r = 5
            elif node.kind == "exit":
                color = "#ff7f50" # Coral/Orange
                r = 5
            else:
                color = "#999" # Grey for junctions
            
            # Highlight Toilets
            if "WC" in node.node_id:
                color = "#e24a90" # Pink for toilets
                
            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="")
            
            # No on-canvas labels (use colour key instead)

        # Update side key + timer overlay
        self._update_room_key()
        self._draw_changeover_timer()

        # Tighten scrollregion to drawn extents (if available)
        try:
            bbox = self.canvas.bbox("all")
            if bbox:
                self.canvas.configure(scrollregion=bbox)
        except Exception:
            pass

    def _update_visualization(self) -> None:
        """Draw agents at current positions using persistent canvas items."""
        if not self.model:
            return
            
        self.canvas.delete("timer")
        
        floorplan = self.controller.state.get("floorplan")
        current_floor = self.floor_var.get()
        
        # Track which agents were updated this frame so we can hide others
        updated_agent_ids = set()
        
        for agent in self.model.agents:
            if agent.active and not agent.completed and agent.current_edge:
                u, v = agent.current_edge
                
                # Only draw if the source node is on the current floor
                if u in self.node_coords:
                    x1, y1 = self.node_coords[u]
                    
                    # Logic for position calculation
                    ax, ay = x1, y1 # Default to source

                    if v in self.node_coords:
                        x2, y2 = self.node_coords[v]
                        
                        # Interpolate
                        edge_data = self.model.graph.get_edge_data(u, v)
                        length = edge_data.get("length_m", 1.0)
                        width_m = edge_data.get("width_m", 2.0)
                        
                        ratio = agent.position_along_edge / length if length > 0 else 0
                        ratio = max(0.0, min(1.0, ratio))
                        
                        ax = x1 + (x2 - x1) * ratio
                        ay = y1 + (y2 - y1) * ratio
                        
                        # --- Visual Smoothing & Lane Logic ---
                        # NEA Improvement: Taper lateral offset near nodes to prevent corner skipping/looping.
                        # Agents move towards the center of the junction before turning, mirroring natural movement.
                        raw_offset = getattr(agent, "lateral_offset", 0.0)
                        
                        # Calculate distance from ends of the edge
                        dist_from_start = ratio * length
                        dist_from_end = (1.0 - ratio) * length
                        taper_zone_m = 1.5 # Distance over which agent merges to center
                        
                        taper_factor = 1.0
                        if dist_from_start < taper_zone_m:
                            taper_factor = dist_from_start / taper_zone_m
                        elif dist_from_end < taper_zone_m:
                            taper_factor = dist_from_end / taper_zone_m
                            
                        # Apply easing (SmoothStep) to the taper for less robotic movement
                        taper_factor = taper_factor * taper_factor * (3 - 2 * taper_factor)
                        
                        current_offset = raw_offset * taper_factor
                        
                        dx = x2 - x1
                        dy = y2 - y1
                        dist = math.sqrt(dx*dx + dy*dy)
                        
                        if dist > 0:
                            # Perpendicular vector (-dy, dx)
                            px = -dy / dist
                            py = dx / dist
                            
                            # Scale by physical width (converted to pixels)
                            width_px = width_m * self.scale
                            
                            # Apply offset directly
                            ax += px * width_px * current_offset
                            ay += py * width_px * current_offset

                        # 3. Screen-space smoothing to reduce sharp corner snaps.
                        # Lower alpha simulates inertia for turns.
                        agent_id_str = str(agent.profile.agent_id)
                        prev = self.agent_visual_pos.get(agent_id_str)
                        if prev is None:
                            smooth_x, smooth_y = ax, ay
                        else:
                            # Exponential smoothing
                            # Alpha 0.4 provides a good balance between responsiveness and curve smoothing
                            alpha = 0.4
                            smooth_x = prev[0] + (ax - prev[0]) * alpha
                            smooth_y = prev[1] + (ay - prev[1]) * alpha

                        self.agent_visual_pos[agent_id_str] = (smooth_x, smooth_y)
                        ax, ay = smooth_x, smooth_y
                        
                    else:
                        # v is NOT on this floor (e.g. stairs)
                        agent_id_str = str(agent.profile.agent_id)
                        self.agent_visual_pos[agent_id_str] = (ax, ay)

                    # --- Color Logic ---
                    # 0-10s: Blue (#3498DB), 10-30s: Orange (#F39C12), >30s: Red (#E74C3C)
                    wait_time = agent.waiting_time_s
                    if wait_time < 10:
                        color = "#3498DB"
                    elif wait_time < 30:
                        color = "#F39C12"
                    else:
                        color = "#E74C3C"
                            
                    # --- Draw/Update Agent ---
                    aid = agent.profile.agent_id
                    canvas_id = self.agent_canvas_ids.get(aid)
                    r = 2
                    
                    if canvas_id is None:
                        # Create new persistent item
                        canvas_id = self.canvas.create_oval(ax-r, ay-r, ax+r, ay+r, fill=color, outline="", tags="agent")
                        self.agent_canvas_ids[aid] = canvas_id
                    else:
                        # Update existing item
                        self.canvas.coords(canvas_id, ax-r, ay-r, ax+r, ay+r)
                        self.canvas.itemconfigure(canvas_id, fill=color, state="normal")
                    
                    updated_agent_ids.add(aid)

        # Hide any agents that are not visible this frame
        for aid, cid in self.agent_canvas_ids.items():
            if aid not in updated_agent_ids:
                self.canvas.itemconfigure(cid, state="hidden")

        self._draw_changeover_timer()


    def _update_room_key(self) -> None:
        """Update the colour legend for node types."""
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            return

        # Rebuild legend (colour key)
        for w in self.legend_items_frame.winfo_children():
            w.destroy()

        subject_colors = {
            "maths": "#2E86AB",
            "english": "#8E44AD",
            "science": "#27AE60",
            "humanities": "#D35400",
            "computer science": "#2C3E50",
            "technology": "#16A085",
            "art": "#C0392B",
            "library": "#7F8C8D",
            "sports hall": "#2980B9",
            "canteen": "#FF9800",
            "seating_area": "#4CAF50",
            "other": "#4a90e2",
        }

        node_type_colors = {
            "toilet": "#e24a90",
            "stairs": "#ffcc00",
            "entrance": "#50c878",
            "junction": "#999999",
            "canteen": "#FF9800",
            "seating_area": "#4CAF50",
        }

        def legend_row(parent, name: str, color: str) -> None:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, anchor="w")
            chip = tk.Label(row, width=2, height=1, bg=color)
            chip.pack(side=tk.LEFT, padx=(0, 6), pady=1)
            ttk.Label(row, text=name).pack(side=tk.LEFT)

        # Node types
        legend_row(self.legend_items_frame, "Toilet", node_type_colors["toilet"])
        legend_row(self.legend_items_frame, "Stairs", node_type_colors["stairs"])
        legend_row(self.legend_items_frame, "Entrance", node_type_colors["entrance"])
        legend_row(self.legend_items_frame, "Junction", node_type_colors["junction"])
        legend_row(self.legend_items_frame, "Canteen", node_type_colors["canteen"])
        legend_row(self.legend_items_frame, "Seating Area", node_type_colors["seating_area"])

        ttk.Separator(self.legend_items_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Room subjects/types
        for name in [
            "maths",
            "english",
            "science",
            "humanities",
            "computer science",
            "technology",
            "art",
            "library",
            "sports hall",
            "other",
        ]:
            legend_row(self.legend_items_frame, name.title(), subject_colors[name])
            
        ttk.Separator(self.legend_items_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        
        # Agent Traffic
        legend_row(self.legend_items_frame, "Delay < 10s", "#3498DB")
        legend_row(self.legend_items_frame, "Delay 10-30s", "#F39C12")
        legend_row(self.legend_items_frame, "Delay > 30s", "#E74C3C")


    def _draw_changeover_timer(self) -> None:
        if not self.model:
            return

        minutes = int(self.changeover_minutes_var.get() or 5)
        changeover_s = max(60, minutes * 60)
        t = float(self.model.time_s)
        remaining = changeover_s - t

        def fmt(secs: float) -> str:
            secs = int(abs(secs))
            mm = secs // 60
            ss = secs % 60
            return f"{mm:02d}:{ss:02d}"

        if remaining >= 0:
            text = f"Changeover {fmt(remaining)}"
        else:
            text = f"Overtime +{fmt(remaining)}"

        cw = self.canvas.winfo_width() or 800
        
        # --- Live Title ---
        mode_name = "Simulation"
        if hasattr(self, "current_sim_mode"):
             mode_name = self.mode_labels.get(self.current_sim_mode, self.current_sim_mode).title()
        
        # Draw Mode Title
        self.canvas.create_text(
            15,
            15,
            text=mode_name,
            anchor="nw",
            fill="#333",
            font=("Segoe UI Semibold", 16),
            tags=("timer",)
        )

        # Draw Timer (Top Right)
        self.canvas.create_text(
            self.canvas.canvasx(cw - 10),
            self.canvas.canvasy(15),
            text=text,
            anchor="ne",
            fill="#222",
            font=("Segoe UI Semibold", 12),
            tags=("timer",),
        )

    def _create_agents_from_scenario(self, scenario_data: Dict[str, Any], scale: float, period_index: int = -1) -> List[AgentProfile]:
        """Generate agents based on loaded scenario configuration.
        
        Args:
            scenario_data: The full scenario configuration.
            scale: Population scaling factor.
            period_index: If >= 0, only generate agents for this specific period index.
                          If -1, generate for all periods (legacy behavior).
        """
        agents = []
        seed = scenario_data.get("random_seed", 42)
        rng = random.Random(seed)
        
        behaviour = scenario_data.get("behaviour", {})
        
        # Helper for sampling distributions
        def sample(spec: Any, default: float = 0.0) -> float:
            if spec is None: return default
            if isinstance(spec, (int, float)): return float(spec)
            if isinstance(spec, dict):
                if "value" in spec: return float(spec["value"])
                if "uniform" in spec: return rng.uniform(spec["uniform"][0], spec["uniform"][1])
                if "lognormal" in spec: return rng.lognormvariate(spec["mean"], spec["sigma"])
                if "normal" in spec: return rng.normalvariate(spec["mean"], spec["sigma"])
            return default

        agent_id_counter = 0
        
        # Helper to parse time
        def parse_time(t_str: str) -> float:
            try:
                h, m = map(int, t_str.split(":"))
                return h * 3600.0 + m * 60.0
            except:
                return 0.0

        # Find earliest start time to normalise
        start_times = []
        all_periods = scenario_data.get("periods", [])
        
        # Filter periods if index specified
        target_periods = []
        if period_index >= 0:
            if period_index < len(all_periods):
                target_periods = [all_periods[period_index]]
            else:
                return [] # Invalid index
        else:
            target_periods = all_periods

        for p in all_periods:
            if "start_time" in p:
                start_times.append(parse_time(p["start_time"]))
        
        min_time = min(start_times) if start_times else 0.0

        # 1. Group movements
        movements_by_chain: Dict[str, List[Dict]] = {}
        standalone_movements: List[Dict] = []
        
        for period in target_periods:
            period_id = period["id"]
            period_start = period.get("start_time", "00:00")
            
            for move in period.get("movements", []):
                count = int(move.get("count", 1) * scale)
                chain_id = move.get("chain_id")
                
                if chain_id:
                    if chain_id not in movements_by_chain:
                        movements_by_chain[chain_id] = []
                    movements_by_chain[chain_id].append({
                        **move, 
                        "period_id": period_id,
                        "period_start_time": period_start
                    })
                else:
                    for _ in range(count):
                        standalone_movements.append({
                            **move, 
                            "period_id": period_id,
                            "period_start_time": period_start
                        })

        # 2. Create Agents from Chains
        for chain_id, moves in movements_by_chain.items():
            agent_id_counter += 1
            
            schedule = []
            
            # Use first move to determine agent properties
            first_move = moves[0]
            
            # Calculate base start time from the first period in the chain
            # If we are running a specific period, we treat its start time as T=0 for the simulation run?
            # OR we keep absolute time?
            # If we run periods sequentially, the simulation resets to T=0 each time.
            # So we should normalise relative to the PERIOD start time, not the global min time.
            
            if period_index >= 0:
                # Relative to THIS period's start
                ref_time = parse_time(first_move.get("period_start_time", "00:00"))
            else:
                # Relative to global start
                ref_time = min_time

            chain_start_time = parse_time(first_move.get("period_start_time", "00:00")) - ref_time
            
            # Jitter departure for the whole chain
            jitter = sample(behaviour.get("depart_jitter_s"), 0.0)
            current_time = chain_start_time + max(0.0, jitter)
            
            for move in moves:
                origin = move["origin"]
                dest = move["destination"]
                delay = move.get("delay_s", 0.0)
                
                # Add delay before scheduling this leg
                current_time += delay
                
                # Validate
                floorplan = self.controller.state["floorplan"]
                if origin not in list(floorplan.node_ids()) or dest not in list(floorplan.node_ids()):
                    continue

                entry = AgentScheduleEntry(
                    period=move["period_id"],
                    origin_room=origin,
                    destination_room=dest,
                    depart_time_s=current_time
                )
                schedule.append(entry)
            
            if not schedule:
                continue
            
            profile = AgentProfile(
                agent_id=f"student_chain_{chain_id}",
                role="student",
                speed_base_mps=sample(behaviour.get("speed_base_mps"), 1.4),
                stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
                optimality_beta=sample(behaviour.get("optimality_beta"), 1.0),
                reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
                detour_probability=sample(behaviour.get("detour_probability"), 0.0),
                schedule=schedule
            )
            agents.append(profile)

        # 3. Create Agents from Standalone
        for move in standalone_movements:
            agent_id_counter += 1
            origin = move["origin"]
            dest = move["destination"]
            
            floorplan = self.controller.state["floorplan"]
            if origin not in list(floorplan.node_ids()) or dest not in list(floorplan.node_ids()):
                continue
            
            # Calculate departure time based on period start
            period_start_s = parse_time(move.get("period_start_time", "00:00"))
            
            if period_index >= 0:
                ref_time = period_start_s # Relative to itself (starts at 0)
            else:
                ref_time = min_time

            relative_start = period_start_s - ref_time
            
            jitter = sample(behaviour.get("depart_jitter_s"), 0.0)
            depart_time = relative_start + max(0.0, jitter)
            
            entry = AgentScheduleEntry(
                period=move["period_id"],
                origin_room=origin,
                destination_room=dest,
                depart_time_s=depart_time
            )
            
            profile = AgentProfile(
                agent_id=f"student_{agent_id_counter}",
                role="student",
                speed_base_mps=sample(behaviour.get("speed_base_mps"), 1.4),
                stairs_penalty=sample(behaviour.get("stairs_penalty", {}).get("student"), 0.5),
                optimality_beta=sample(behaviour.get("optimality_beta"), 1.0),
                reroute_interval_ticks=int(sample(behaviour.get("reroute_interval_ticks"), 10)),
                detour_probability=sample(behaviour.get("detour_probability"), 0.0),
                schedule=[entry]
            )
            agents.append(profile)
                    
        return agents

    def _start_sequence(self) -> None:
        """Begin execution of selected simulation modes in sequence."""
        # 1. Identify selected modes
        selected_modes = []
        # Fixed order of execution:
        if self.mode_vars["start_of_day"].get(): selected_modes.append("start_of_day")
        if self.mode_vars["lesson_changeover"].get(): selected_modes.append("lesson_changeover")
        if self.mode_vars["break_time"].get(): selected_modes.append("break_time")
        
        if not selected_modes:
            messagebox.showwarning("Select Mode", "Please select at least one simulation type to run.")
            return

        # 2. Validation (e.g., Break Time needs Canteen)
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            messagebox.showerror("Error", "No floor plan loaded.")
            return

        if "break_time" in selected_modes:
            canteen_nodes = [n for n in floorplan.nodes if n.kind == "canteen"]
            if not canteen_nodes:
                messagebox.showerror(
                    "Missing Canteen",
                    "Break Time mode requires at least one canteen in the layout.\n"
                    "Please add a canteen using the Editor before running Break Time simulation."
                )
                return

        # 3. Initialize Queue
        self.run_queue = selected_modes
        self.sequence_results = {} # Map[mode -> MetricsCollector]
        self.controller.state["all_results"] = {} # Clear old results

        # 4. Start First
        self.start_btn.config(state="disabled")
        self.next_btn.config(state="disabled")
        self._run_next_in_queue()

    def _run_next_in_queue(self) -> None:
        """Run the next simulation in the queue."""
        if not self.run_queue:
            # All done!
            self._on_sequence_completed()
            return

        mode = self.run_queue.pop(0)
        self.current_sim_mode = mode
        
        # Determine mode display name
        mode_name = self.mode_labels.get(mode, mode)
        self.status_var.set(f"Preparing: {mode_name}...")
        self.update_idletasks() # Force UI update

        # Generate agents and config for this mode
        try:
            self._setup_single_run(mode, mode_name)
        except Exception as e:
            messagebox.showerror("Simulation Error", f"Failed to start {mode_name}: {e}")
            self._on_sequence_completed() # Abort

    def _setup_single_run(self, mode: str, mode_name: str) -> None:
        """Generate agents and configure model for a single run."""
        config_data = self.controller.state.get("scenario_config", {})
        floorplan = self.controller.state.get("floorplan")
        disabled_edges = list(self.controller.state.get("disabled_edges", []))
        
        minutes = int(self.changeover_minutes_var.get() or 5)
        duration = max(60, minutes * 60)
        seed = config_data.get("seed", 42)
        scale = config_data.get("scale", 1.0)
        scenario_data = config_data.get("data")
        
        # Robust fallback for scenario data
        if not scenario_data and mode == "lesson_changeover":
            try:
                from smartflow.io.importers import load_scenario
                floorplan_path = self.controller.state.get("floorplan_path")
                if floorplan_path:
                    path_obj = Path(floorplan_path)
                    scen_path = path_obj.with_name(path_obj.stem + "_scenario.json")
                    if scen_path.exists():
                        scenario_data = load_scenario(scen_path)
            except Exception:
                pass

        agents = []
        
        # --- GENERATION LOGIC ---
        if mode == "break_time":
            agents = generate_break_time_agents(floorplan, seed, scale, duration)
        elif mode == "start_of_day":
            agents = generate_start_of_day_agents(floorplan, seed, scale)
        elif mode == "lesson_changeover":
            # User Request Check: "IF I HAVE TICKED OFF LESSON CHANGEOVER, ALL STUDENTS SHOULD START IN THE ROOMS"
            # Previously this tried to load from a scenario file (Period 0), which often contained "Start of Day" logic.
            # We now Enforce procedural generation for consistency with "Start of Day" and "Break Time" modes.
            
            # Use smart lesson changeover generation (Room -> Room)
            # User requirement: ~15-25 students per class.
            room_count = len([n for n in floorplan.nodes if n.kind == "room"])
            if room_count == 0: room_count = 5 # Fallback
            
            # Average 20 students per room
            base_students = room_count * 20
            agent_count = int(base_students * scale)
            
            agents = generate_lesson_changeover_agents(floorplan, agent_count, seed)

        if not agents:
            messagebox.showwarning("Warning", f"No agents generated for {mode_name}. Skipping.")
            self._run_next_in_queue()
            return

        # Store mode info
        self.controller.state["last_sim_mode"] = mode
        self.controller.state["current_sim_name"] = mode_name

        tick_seconds = 0.05
        sim_config = SimulationConfig(
            tick_seconds=tick_seconds,
            transition_window_s=float(duration),
            random_seed=seed, # Could offset seed by mode index
            disabled_edges=disabled_edges,
            lesson_changeover_s=float(duration),
            k_paths=3, # Enable alternative routes (second fastest) for stochastic agents
        )

        # Route caching
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH
            from smartflow.io import db as dbio
            floorplan_path = self.controller.state.get("floorplan_path")
            if floorplan_path:
                sim_config.route_cache_db_path = str(DEFAULT_DB_PATH)
                sim_config.route_cache_layout_hash = dbio.compute_layout_hash(Path(floorplan_path))
        except Exception:
            pass

        self.model = SmartFlowModel(floorplan, agents, sim_config)
        
        # Setup Runtime
        max_sim_s = max(float(duration) * 2.0, float(duration) + 60.0)
        self.total_ticks = int(max_sim_s / tick_seconds)
        self.current_tick = 0
        self.agent_offsets.clear()
        self.agent_visual_pos.clear()
        
        self.is_running = True
        self.stop_btn.config(state="normal", text="Pause")
        
        # Loading Indicator Logic
        if bool(self.skip_animation_var.get()):
            self.status_var.set(f"Running {mode_name} (Fast Mode)...")
            self.loading_label.pack(side=tk.LEFT, padx=8) # Ensure visible
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2 or 400,
                self.canvas.winfo_height() // 2 or 300,
                text=f"⏳ Running {mode_name}...\nPlease wait.",
                font=("Segoe UI", 14),
                fill="#555",
                justify="center",
            )
            self.update_idletasks()
        else:
            self.status_var.set(f"Running: {mode_name} (0/{self.total_ticks})")
            self._setup_visualization() # Clear and prep canvas
        
        self._run_step()

    def _on_sequence_completed(self) -> None:
        """Called when all selected modes have finished."""
        self.is_running = False
        self.status_var.set("All selected simulations completed.")
        self.start_btn.config(state="normal", text="Run Again")
        self.stop_btn.config(state="disabled")
        
        # Store all results in state for ResultsView
        self.controller.state["all_results"] = self.sequence_results
        
        # Compatibility: Set the last run as the "main" result
        if self.sequence_results:
            last_key = list(self.sequence_results.keys())[-1]
            self.controller.state["simulation_results"] = self.sequence_results[last_key]
        
        self.next_btn.config(state="normal", text="Next: Results >")
        self._sync_next_buttons()

    def _sync_next_buttons(self) -> None:
        """Mirror bottom-nav next button state into the playback-area button."""
        if not hasattr(self, "playback_next_btn"):
            return
        try:
            self.playback_next_btn.config(
                state=str(self.next_btn.cget("state")),
                text=str(self.next_btn.cget("text")),
                command=self.next_btn.cget("command"),
            )
        except Exception:
            pass


    def _worker_loop(self) -> None:
        """Background thread for simulation logic."""
        while self.is_running and self.model and not self.model.is_complete:
            # Check stop event
            if self._stop_event.is_set():
                break

            # Check bounds
            if self.current_tick >= self.total_ticks:
                break
            
            # --- Skip Animation (Fast Mode) ---
            if bool(self.skip_animation_var.get()):
                # Run faster: Process a batch of steps (e.g., 50) per loop iteration
                batch_size = 50
                for _ in range(batch_size):
                    if self.current_tick >= self.total_ticks or self.model.is_complete: 
                        break
                    with self.model_lock:
                        self.model.step()
                        self.current_tick += 1
                
                # Tiny yield to let UI thread breathe if needed, but mostly stay busy
                # No targeted sleep, just run as fast as CPU permits
                time.sleep(0.0001) 
                
            else:
                # --- Realistic Speed Control ---
                # To simulate reality, we must respect tick_seconds vs wall time.
                # Default tick is 0.05s.
                target_tick_s = 0.05 
                if hasattr(self.model, "config") and hasattr(self.model.config, "tick_seconds"):
                    target_tick_s = float(self.model.config.tick_seconds)
                
                # Apply playback multiplier
                mult = float(self.playback_mult_var.get() or 1.0)
                playback_speed = max(0.5, min(4.0, mult))
                
                # How long *should* this tick take in real wall seconds?
                # e.g. tick=0.05s, 1.0x speed => wait 0.05s
                # e.g. tick=0.05s, 2.0x speed => wait 0.025s
                desired_wall_dt = target_tick_s / playback_speed
                
                start_t = time.perf_counter()
                
                with self.model_lock:
                    self.model.step()
                    self.current_tick += 1
                
                # Sleep the remainder to match realistic speed
                elapsed = time.perf_counter() - start_t
                sleep_time = max(0.0, desired_wall_dt - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
    def _run_step(self) -> None:
        """UI loop: Updates visualization and status from background thread."""
        if not self.is_running or not self.model:
            return
            
        # Ensure worker is running
        if self._active_worker_thread is None or not self._active_worker_thread.is_alive():
            self._active_worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._active_worker_thread.start()

        # Check for completion or timeout
        # Using a lock here to safely read 'current_tick' and 'is_complete' which change in thread
        is_complete = False
        with self.model_lock:
            if self.model.is_complete or self.current_tick >= self.total_ticks:
                is_complete = True
        
        if is_complete:
            self._finish_simulation()
            return
        
        # Update UI Progress
        progress = (self.current_tick / self.total_ticks) * 100
        self.progress_var.set(progress)
        
        if bool(self.skip_animation_var.get()):
            # Minimal status update for fast mode
            pct = int(progress)
            self.status_var.set(f"Computing... {pct}% ({self.current_tick}/{self.total_ticks})")
            # In fast mode, we update UI less frequently (e.g. 10fps) to keep CPU free for worker
            self.after(100, self._run_step)
        else:
            self.status_var.set(f"Running... ({self.current_tick}/{self.total_ticks})")
            # Update visualisation - acquire lock to read agents consistent state
            with self.model_lock:
                self._update_visualization()
            
            # Schedule next UI update (30fps target)
            self.after(33, self._run_step)

    def _stop_simulation(self) -> None:
        """Pause the running simulation."""
        self.is_running = False
        self.status_var.set("Simulation paused. Press Space or Resume to continue.")
        self.start_btn.config(state="normal", text="Resume", command=self._resume_simulation)
        self.stop_btn.config(state="disabled")

    def _resume_simulation(self) -> None:
        """Resume a paused simulation."""
        if self.model is None or self.current_tick >= self.total_ticks:
            return
        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal", text="Pause")
        self.status_var.set(f"Resuming simulation... ({self.current_tick}/{self.total_ticks})")
        self._run_step()

    def _finish_simulation(self) -> None:
        """Finalise results and proceed to next in queue."""
        self.is_running = False
        self._stop_event.set()
        
        # Hide loading indicator
        try:
            self.loading_label.pack_forget()
        except Exception:
            pass
        
        if not self.model:
            # Should not happen, but safe fallback
            self._run_next_in_queue()
            return

        # --- METRICS COLLECTION ---
        for state in self.model.agents:
            # 1. Determine Lateness
            is_late = bool(getattr(state, "is_late", False))
            if not state.completed and state.active:
                is_late = True
            
            scheduled = getattr(state, "scheduled_arrival_s", None)
            actual = getattr(state, "actual_arrival_s", None)
            
            # 2. Determine Delay
            # Use accumulated waiting time (congestion penalty) as the delay metric.
            # This ensures we capture congestion even if agents arrive on time (due to generous buffers).
            delay_s = state.waiting_time_s
            
            # Record
            self.model.collector.record_agent(
                state.profile.agent_id,
                AgentMetrics(
                    travel_time_s=state.travel_time_s,
                    path_nodes=state.path_nodes,
                    delay_s=delay_s,
                    scheduled_arrival_s=scheduled,
                    actual_arrival_s=actual,
                    is_late=is_late,
                )
            )
        
        summary = self.model.collector.finalize()
        
        # --- STORE RESULT ---
        if hasattr(self, "current_sim_mode"):
             self.sequence_results[self.current_sim_mode] = self.model.collector
             print(f"Finished {self.current_sim_mode}. Avg Delay: {summary.mean_travel_time_s}")


        # --- NEXT ---
        # Short pause before next? Or instant?
        self.after(500, self._run_next_in_queue)

    def _go_next(self) -> None:
        """Navigate to results."""
        self.controller.show_frame("ResultsView")
