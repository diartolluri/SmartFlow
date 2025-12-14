"""View for running simulations."""

from __future__ import annotations

import random
import math
import tkinter as tk
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
        
        self.current_period_index = 0
        self.scenario_periods = []
        
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

        self.start_btn = ttk.Button(control_frame, text="Start Simulation", command=self._start_simulation)
        self.start_btn.pack(fill=tk.X, pady=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self._stop_simulation, state="disabled")
        self.stop_btn.pack(fill=tk.X, pady=5)

        # Speed Control
        speed_frame = ttk.LabelFrame(left_panel, text="Playback Speed", padding=10)
        speed_frame.pack(fill=tk.X, pady=10)
        
        self.speed_var = tk.DoubleVar(value=50.0) # Default delay in ms
        
        ttk.Label(speed_frame, text="Fast").pack(side=tk.LEFT)
        self.speed_scale = ttk.Scale(
            speed_frame, 
            from_=10, 
            to=200, 
            variable=self.speed_var, 
            orient=tk.HORIZONTAL,
            command=lambda v: None # No-op, just updates var
        )
        self.speed_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(speed_frame, text="Slow").pack(side=tk.LEFT)

        # Floor Control
        self.floor_frame = ttk.LabelFrame(left_panel, text="Floor View", padding=10)
        self.floor_frame.pack(fill=tk.X, pady=10)
        
        self.floor_var = tk.IntVar(value=0)
        # Buttons will be populated in update_view()

        # --- Right Panel (Visualisation) ---
        
        viz_frame = ttk.LabelFrame(right_panel, text="Live View", padding=5)
        viz_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(viz_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
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
        
        # Calculate scale to fit
        scale_x = cw / width_m if width_m > 0 else 1.0
        scale_y = ch / height_m if height_m > 0 else 1.0
        self.scale = min(scale_x, scale_y)
        
        # Center offset
        self.offset_x = -min_x * self.scale + (cw - width_m * self.scale) / 2
        self.offset_y = -min_y * self.scale + (ch - height_m * self.scale) / 2
        
        # Helper to transform coords
        def to_screen(x: float, y: float) -> Tuple[float, float]:
            # Invert Y for screen coords
            return (x * self.scale + self.offset_x, ch - (y * self.scale + self.offset_y))

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
            
            # Colour coding
            if node.kind == "room":
                color = "#4a90e2" # Blue
            elif node.kind == "entry":
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
            
            # Labels for rooms, entry, exit
            if node.kind in ["room", "entry", "exit"]:
                self.canvas.create_text(x, y-10, text=node.label, font=("Arial", 8), fill="#333")

    def _update_visualization(self) -> None:
        """Draw agents at current positions."""
        if not self.model:
            return
            
        self.canvas.delete("agent")
        
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
                optimality_beta=1.0,
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

        duration = config_data.get("duration", 300)
        seed = config_data.get("seed", 42)
        scale = config_data.get("scale", 1.0)
        beta = config_data.get("beta", 1.0)
        scenario_data = config_data.get("data")
        
        # Determine periods
        if scenario_data:
            self.scenario_periods = scenario_data.get("periods", [])
            
            # Inject user-defined beta into behaviour as a distribution
            # This ensures it varies per student
            if "behaviour" not in scenario_data:
                scenario_data["behaviour"] = {}
            
            # Use a normal distribution centered on the user's choice
            # Sigma = 20% of the mean, or at least 0.5
            sigma = max(0.5, beta * 0.2)
            scenario_data["behaviour"]["optimality_beta"] = {
                "normal": {"mean": beta, "sigma": sigma}
            }
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
        
        sim_config = SimulationConfig(
            tick_seconds=0.05, # Finer resolution (20 ticks/sec) for smoother movement
            transition_window_s=float(duration),
            random_seed=seed + self.current_period_index, # Vary seed per period
            beta=beta,
            disabled_edges=disabled_edges
        )
        
        self.model = SmartFlowModel(floorplan, agents, sim_config)
        self.total_ticks = int(duration / 0.05)
        self.current_tick = 0
        self.agent_offsets.clear() # Reset offsets for new run
        
        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.next_btn.config(state="disabled", text="Next >") # Reset text
        
        status_msg = f"Running: {period_name} (0/{self.total_ticks})"
        self.status_var.set(status_msg)
        
        # Initialise visualisation
        self._setup_visualization()
        
        self._run_step()

    def _run_next_period(self) -> None:
        """Start the next period in the sequence."""
        self.current_period_index += 1
        self._start_simulation(continue_sequence=True)

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
        # Adjust delay to match tick rate if possible
        # Tick = 0.05s (50ms). If speed slider is 50ms, we run at 1x speed.
        delay = int(self.speed_var.get())
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
                )
            )
        self.model.collector.finalize()
        
        # Store results (accumulate?)
        # For now, just overwrite. The ResultsView might need updates to handle multiple runs.
        self.controller.state["simulation_results"] = self.model.collector
        
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        
        # Check if there are more periods
        if self.scenario_periods and self.current_period_index < len(self.scenario_periods) - 1:
            next_period = self.scenario_periods[self.current_period_index + 1]
            next_name = next_period.get("id", f"Period {self.current_period_index + 2}")
            
            self.status_var.set(f"Period complete. Ready for: {next_name}")
            self.next_btn.config(state="normal", text=f"Run: {next_name} >", command=self._run_next_period)
            
            messagebox.showinfo("Period Complete", f"Finished period {self.current_period_index + 1}.\nClick 'Run: {next_name}' to continue.")
        else:
            self.status_var.set("All simulations complete!")
            self.next_btn.config(state="normal", text="Next: Results >", command=self._go_next)
            messagebox.showinfo("Success", "Simulation completed successfully.")

    def _go_next(self) -> None:
        """Navigate to results."""
        self.controller.show_frame("ResultsView")
