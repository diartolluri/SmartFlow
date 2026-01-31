"""View for running simulations."""

from __future__ import annotations

import random
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, List, Dict, Any, Tuple

from smartflow.core.agents import AgentProfile, AgentScheduleEntry
from smartflow.core.metrics import AgentMetrics
from smartflow.core.model import SimulationConfig, SmartFlowModel
from smartflow.core.scenario_loader import create_agents_from_scenario

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

        # Playback + lesson changeover configuration
        self.playback_mult_var = tk.DoubleVar(value=1.0)
        self.playback_label_var = tk.StringVar(value="1.0×")
        self.changeover_minutes_var = tk.IntVar(value=5)
        
        self.current_period_index = 0
        self.scenario_periods = []

        # Track default start button behaviour so we can temporarily repurpose it
        # for "Run next period" when sequencing scenario periods.
        self._start_button_default_text = "Start Simulation"
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialise UI components."""
        # Header
        header = ttk.Label(self, text="Step 3: Run Simulation", font=("Segoe UI", 16, "bold"))
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

        # Controls
        control_frame = ttk.Frame(left_panel)
        control_frame.pack(pady=20)

        self.start_btn = ttk.Button(control_frame, text=self._start_button_default_text, command=self._start_simulation)
        self.start_btn.pack(fill=tk.X, pady=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self._stop_simulation, state="disabled")
        self.stop_btn.pack(fill=tk.X, pady=5)

        # Lesson changeover settings
        changeover_frame = ttk.LabelFrame(left_panel, text="Lesson Changeover", padding=10)
        changeover_frame.pack(fill=tk.X, pady=10)

        ttk.Label(changeover_frame, text="Timer (minutes):").pack(anchor="w")
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

        ttk.Label(self.legend_frame, text="Colour Key", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.legend_items_frame = ttk.Frame(self.legend_frame)
        self.legend_items_frame.pack(fill=tk.X, pady=(4, 8))

        ttk.Label(self.key_inner, text="Rooms (per floor)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.key_list = tk.Listbox(self.key_inner, height=10)
        self.key_list.pack(fill=tk.BOTH, expand=True)

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
                "canteen": "#F1C40F",
                "other": "#4a90e2",
            }
            
            # Colour coding
            if node.kind == "room":
                color = subject_colors.get(subject, subject_colors["other"])
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
        """Draw agents at current positions."""
        if not self.model:
            return
            
        self.canvas.delete("agent")
        self.canvas.delete("timer")
        
        floorplan = self.controller.state.get("floorplan")
        current_floor = self.floor_var.get()
        
        for agent in self.model.agents:
            if agent.active and not agent.completed and agent.current_edge:
                u, v = agent.current_edge
                
                # Check if agent is on current floor
                # We check the source node 'u'. If 'u' is on this floor, we show them.
                # This handles stairs: if u is on F0 and v is on F1, they show on F0 until they reach v.
                # If u is on F1 and v is on F0, they show on F1.
                
                # We need to look up the node object to check floor
                # Optimization: Cache node floors? Or just look up in floorplan.nodes list (slow)
                # Better: Use self.node_coords which ONLY contains nodes on current floor.
                
                if u in self.node_coords:
                    x1, y1 = self.node_coords[u]
                    
                    # If v is also on this floor, we interpolate normally
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
                        
                        # 1. Lateral Offset (Lanes) with Smoothing
                        target_offset = getattr(agent, "lateral_offset", 0.0)
                        
                        # Retrieve previous visual offset
                        current_visual_offset = self.agent_offsets.get(agent.profile.agent_id, target_offset)
                        
                        # Lerp towards target (Smoothing factor 0.1 per frame)
                        # If frame rate is high, this is smooth. If low, it might be slow.
                        # Let's use a fixed step approach or time-based?
                        # Simple lerp: new = old + (target - old) * factor
                        lerp_factor = 0.1
                        new_visual_offset = current_visual_offset + (target_offset - current_visual_offset) * lerp_factor
                        
                        # Store for next frame
                        self.agent_offsets[agent.profile.agent_id] = new_visual_offset
                        
                        # 2. Wobble (Natural Sway) - DISABLED
                        # sin(time * speed + phase)
                        # Reduced frequency (3.0) and amplitude (0.02) to stop "shaking" look
                        # phase = hash(agent.profile.agent_id) % 628 / 100.0
                        # wobble = math.sin(self.model.time_s * 3.0 + phase) * 0.02 
                        wobble = 0.0
                        
                        total_offset = new_visual_offset + wobble

                        dx = x2 - x1
                        dy = y2 - y1
                        dist = math.sqrt(dx*dx + dy*dy)
                        
                        if dist > 0:
                            # Perpendicular vector (-dy, dx)
                            px = -dy / dist
                            py = dx / dist
                            
                            # Scale by physical width (converted to pixels)
                            width_px = width_m * self.scale
                            
                            # Apply offset
                            ax += px * width_px * total_offset
                            ay += py * width_px * total_offset
                            
                        # Draw agent
                        color = "red"
                        self.canvas.create_oval(ax-2, ay-2, ax+2, ay+2, fill=color, outline="", tags="agent")
                        
                    else:
                        # v is NOT on this floor (e.g. stairs going UP/DOWN to another floor)
                        # We show them at u (or fading out?)
                        # For now, just show them at u, maybe slightly offset towards "stairs" direction if we knew it
                        # But we don't have coords for v.
                        # Let's just draw them at u.
                        
                        ax, ay = x1, y1
                        color = "orange" # Show transition colour?
                        self.canvas.create_oval(ax-2, ay-2, ax+2, ay+2, fill=color, outline="", tags="agent")

        self._draw_changeover_timer()


    def _update_room_key(self) -> None:
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            return
        current_floor = int(self.floor_var.get())

        if not hasattr(self, "key_list"):
            return

        self.key_list.delete(0, tk.END)
        rooms = [n for n in floorplan.nodes if n.kind == "room" and int(n.floor) == current_floor]
        rooms.sort(key=lambda n: str(n.node_id))

        for n in rooms:
            try:
                subj = str((n.metadata or {}).get("subject", "other")).lower()
            except Exception:
                subj = "other"
            self.key_list.insert(tk.END, f"{n.node_id} — {subj}")

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
            "canteen": "#F1C40F",
            "other": "#4a90e2",
        }

        node_type_colors = {
            "toilet": "#e24a90",
            "stairs": "#ffcc00",
            "entrance": "#50c878",
            "junction": "#999999",
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
            "canteen",
            "other",
        ]:
            legend_row(self.legend_items_frame, name.title(), subject_colors[name])


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
        self.canvas.create_text(
            self.canvas.canvasx(cw - 10),
            self.canvas.canvasy(10),
            text=text,
            anchor="ne",
            fill="#222",
            font=("Segoe UI", 11, "bold"),
            tags=("timer",),
        )

    def _generate_agents(self, count: int, seed: int) -> List[AgentProfile]:
        """Generate random agents for testing."""
        rng = random.Random(seed)
        floorplan = self.controller.state["floorplan"]
        nodes = list(floorplan.node_ids())
        
        agents = []
        for i in range(count):
            origin = rng.choice(nodes)
            dest = rng.choice(nodes)
            while dest == origin:
                dest = rng.choice(nodes)
                
            entry = AgentScheduleEntry(
                period="Period 1",
                origin_room=origin,
                destination_room=dest,
                depart_time_s=rng.uniform(0, 60) # Stagger starts
            )
            
            profile = AgentProfile(
                agent_id=f"student_{i}",
                role="student",
                speed_base_mps=rng.normalvariate(1.4, 0.2),
                stairs_penalty=0.5,
                # Per-agent varied optimality (agent-based heterogeneity)
                optimality_beta=max(0.1, min(5.0, rng.normalvariate(1.0, 0.5))),
                reroute_interval_ticks=10,
                detour_probability=0.1,
                schedule=[entry]
            )
            agents.append(profile)
        return agents

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

    def _start_simulation(self, continue_sequence: bool = False) -> None:
        """Initialise and start the simulation loop."""
        config_data = self.controller.state.get("scenario_config", {})
        floorplan = self.controller.state.get("floorplan")
        disabled_edges = list(self.controller.state.get("disabled_edges", []))
        
        if not floorplan:
            messagebox.showerror("Error", "No floor plan loaded.")
            return

        # Treat duration as the lesson changeover timer.
        # If scenario_config provides a duration (seconds), seed the minutes spinner once.
        try:
            provided = float(config_data.get("duration", 300))
            if provided > 0 and not continue_sequence:
                self.changeover_minutes_var.set(max(1, int(round(provided / 60.0))))
        except Exception:
            pass

        minutes = int(self.changeover_minutes_var.get() or 5)
        duration = max(60, minutes * 60)
        seed = config_data.get("seed", 42)
        scale = config_data.get("scale", 1.0)
        scenario_data = config_data.get("data")

        # Robust fallback: if the scenario wasn't loaded/saved in ConfigView (common after
        # switching layouts), try to auto-load [layout]_scenario.json so multi-period
        # runs (e.g. lesson changeover) are available.
        if not scenario_data:
            try:
                from smartflow.io.importers import load_scenario

                floorplan_path = self.controller.state.get("floorplan_path")
                if floorplan_path:
                    path_obj = Path(floorplan_path)
                    scen_path = path_obj.with_name(path_obj.stem + "_scenario.json")
                    if scen_path.exists():
                        scenario_data = load_scenario(scen_path)
                        updated = dict(config_data)
                        updated["data"] = scenario_data
                        self.controller.state["scenario_config"] = updated
            except Exception:
                pass
        
        # Determine periods
        if scenario_data:
            self.scenario_periods = scenario_data.get("periods", [])
        else:
            self.scenario_periods = []

        if not continue_sequence:
            self.current_period_index = 0
            # Reset metrics collector if needed, or we can append later
        
        # Generate agents
        if scenario_data and self.scenario_periods:
            # Run specific period
            current_period = self.scenario_periods[self.current_period_index]
            period_name = current_period.get("id", f"Period {self.current_period_index + 1}")
            
            print(f"Starting simulation for period: {period_name}")
            
            agents = create_agents_from_scenario(
                scenario_data, 
                floorplan, 
                scale, 
                period_index=self.current_period_index
            )
            if not agents:
                messagebox.showwarning("Warning", f"No agents generated for {period_name}.")
                # Should we continue?
        else:
            # Legacy/Random mode
            agent_count = int(50 * scale) # Base 50 agents
            agents = self._generate_agents(agent_count, seed)
            period_name = "Random Simulation"
        
        tick_seconds = 0.05  # 20 ticks/sec
        sim_config = SimulationConfig(
            tick_seconds=tick_seconds,
            transition_window_s=float(duration),
            random_seed=seed + self.current_period_index, # Vary seed per period
            disabled_edges=disabled_edges
        )

        # Lesson changeover / lateness realism
        sim_config.lesson_changeover_s = float(duration)

        # Enable SQLite-backed route caching (deterministic routing only).
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

        # Allow the simulation to continue after the timer hits 0 so late arrivals can finish.
        max_sim_s = max(float(duration) * 2.0, float(duration) + 60.0)
        self.total_ticks = int(max_sim_s / tick_seconds)
        self.current_tick = 0
        self.agent_offsets.clear() # Reset offsets for new run
        
        self.is_running = True
        self.start_btn.config(state="disabled", text=self._start_button_default_text, command=self._start_simulation)
        self.stop_btn.config(state="normal")
        self.next_btn.config(state="disabled", text="Next >") # Reset text
        self._sync_next_buttons()
        
        status_msg = f"Running: {period_name} (0/{self.total_ticks})"
        self.status_var.set(status_msg)
        
        # Initialise visualisation
        self._setup_visualization()
        
        self._run_step()

    def _run_next_period(self) -> None:
        """Start the next period in the sequence."""
        self.current_period_index += 1
        self._start_simulation(continue_sequence=True)

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

    def _run_step(self) -> None:
        """Execute one simulation step."""
        if not self.is_running or not self.model:
            return
            
        # Check for completion or timeout
        if self.model.is_complete or self.current_tick >= self.total_ticks:
            self._finish_simulation()
            return
            
        self.model.step()
        self.current_tick += 1
        
        # Update UI
        progress = (self.current_tick / self.total_ticks) * 100
        self.progress_var.set(progress)
        self.status_var.set(f"Running simulation... ({self.current_tick}/{self.total_ticks})")
        
        # Update visualisation
        self._update_visualization()
        
        # Schedule next step based on speed slider
        # Adjust delay to match tick rate.
        # Tick = 0.05s (50ms). 1.0x => 50ms, 0.5x => 100ms, 4.0x => 12ms.
        mult = float(self.playback_mult_var.get() or 1.0)
        mult = max(0.5, min(4.0, mult))
        tick_seconds = float(getattr(getattr(self.model, "config", None), "tick_seconds", 0.05))
        delay = max(1, int(round((tick_seconds * 1000.0) / mult)))
        self.after(delay, self._run_step)

    def _stop_simulation(self) -> None:
        """Stop the running simulation."""
        self.is_running = False
        self.status_var.set("Simulation stopped.")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _finish_simulation(self) -> None:
        """Finalise results and enable navigation."""
        self.is_running = False
        
        if not self.model:
            return

        # Collect final metrics manually since we didn't use model.run()
        for state in self.model.agents:
             self.model.collector.record_agent(
                state.profile.agent_id,
                AgentMetrics(
                    travel_time_s=state.travel_time_s,
                    path_nodes=state.path_nodes,
                    delay_s=state.waiting_time_s,
                    scheduled_arrival_s=getattr(state, "scheduled_arrival_s", None),
                    actual_arrival_s=getattr(state, "actual_arrival_s", None),
                    is_late=bool(getattr(state, "is_late", False)),
                )
            )
        self.model.collector.finalize()
        
        # Store results (accumulate?)
        # For now, just overwrite. The ResultsView might need updates to handle multiple runs.
        self.controller.state["simulation_results"] = self.model.collector

        # Auto-save results for NEA evidence and later comparison.
        # If the user created an unsaved layout in the editor, floorplan_path may be None.
        try:
            from smartflow.io.persistence import DEFAULT_DB_PATH, save_current_run

            floorplan_path = self.controller.state.get("floorplan_path")
            scenario_config = self.controller.state.get("scenario_config") or {}
            run_id = save_current_run(
                floorplan_path=floorplan_path,
                scenario_config=scenario_config,
                results=self.model.collector,
                db_path=DEFAULT_DB_PATH,
            )
            self.controller.state["last_run_id"] = run_id
            self.controller.state["last_run_auto_saved"] = True
        except Exception:
            # Silent failure: user can still manually save from ResultsView.
            self.controller.state["last_run_auto_saved"] = False
        
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        
        # Check if there are more periods
        if self.scenario_periods and self.current_period_index < len(self.scenario_periods) - 1:
            next_period = self.scenario_periods[self.current_period_index + 1]
            next_name = next_period.get("id", f"Period {self.current_period_index + 2}")
            
            self.status_var.set(f"Period complete. Ready for: {next_name}")
            self.next_btn.config(state="normal", text=f"Run: {next_name} >", command=self._run_next_period)
            self._sync_next_buttons()

            # Make the next action obvious/accessible: repurpose the large left button too.
            self.start_btn.config(state="normal", text=f"Run: {next_name}", command=self._run_next_period)
            
            messagebox.showinfo("Period Complete", f"Finished period {self.current_period_index + 1}.\nClick 'Run: {next_name}' to continue.")
        else:
            self.status_var.set("All simulations complete!")
            self.next_btn.config(state="normal", text="Next: Results >", command=self._go_next)
            self._sync_next_buttons()

            # Restore default start behaviour for a fresh run.
            self.start_btn.config(state="normal", text=self._start_button_default_text, command=self._start_simulation)
            messagebox.showinfo("Success", "Simulation completed successfully.")

    def _go_next(self) -> None:
        """Navigate to results."""
        self.controller.show_frame("ResultsView")
