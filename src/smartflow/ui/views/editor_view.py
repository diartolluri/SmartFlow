"""
Interactive Floor Plan Editor.
Allows users to draw nodes and edges, configure properties, and save to JSON.
"""

from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from tkinter import filedialog
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..app import SmartFlowApp

# Visual constants
SCALE_PX_PER_M = 5.0  # 1 meter = 5 pixels
NODE_RADIUS = 6
SELECTION_COLOR = "#0078D7"

TOOL_SELECT = "select"
TOOL_ROOM = "room"
TOOL_TOILET = "toilet"
TOOL_ENTRANCE = "entrance"
TOOL_JUNCTION = "junction"
TOOL_CONNECT = "connect"
TOOL_CONNECT_DIRECTED = "connect_directed"
TOOL_ONEWAY = "oneway"
TOOL_DELETE = "delete"

class EditorView(ttk.Frame):
    """Canvas-based editor for creating floor plans."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=0)
        self.controller = controller
        
        # Data model
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.next_id = 1
        
        # State
        self.current_tool = TOOL_SELECT
        self.selected_item: Optional[str] = None # ID of selected node/edge
        self.drag_data: Dict[str, Any] = {"x": 0, "y": 0, "item": None}
        self.connection_start: Optional[str] = None # Node ID
        
        self._init_ui()

    def _init_ui(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(toolbar, text="Tools:").pack(side=tk.LEFT, padx=5)
        
        self.tool_var = tk.StringVar(value=TOOL_SELECT)
        
        tools = [
            ("Select/Move", TOOL_SELECT),
            ("Add Room", TOOL_ROOM),
            ("Add Toilet", TOOL_TOILET),
            ("Add Entrance", TOOL_ENTRANCE),
            ("Add Junction", TOOL_JUNCTION),
            ("Undirected Path", TOOL_CONNECT),
            ("Directed Path", TOOL_CONNECT_DIRECTED),
            ("Toggle/Flip Direction", TOOL_ONEWAY),
            ("Delete", TOOL_DELETE),
        ]
        
        for text, mode in tools:
            btn = ttk.Radiobutton(
                toolbar, 
                text=text, 
                variable=self.tool_var, 
                value=mode,
                command=self._on_tool_change
            )
            btn.pack(side=tk.LEFT, padx=5)
            
        # Action Buttons
        ttk.Button(toolbar, text="Clear All", command=self._clear_canvas).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="Save Layout & Scenario", command=self._save_project).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="Exit", command=lambda: self.controller.show_frame("LayoutView")).pack(side=tk.RIGHT, padx=5)

        # Canvas
        self.canvas = tk.Canvas(self, bg="#1e1e1e", cursor="arrow", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Events
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_tool_change(self) -> None:
        self.current_tool = self.tool_var.get()
        self.selected_item = None
        self.connection_start = None
        self._redraw()

    def _get_node_at(self, x: float, y: float) -> Optional[str]:
        """Find node ID under mouse."""
        # Simple hit testing
        for node in self.nodes:
            nx, ny = self._world_to_screen(node["pos"])
            dist = math.hypot(nx - x, ny - y)
            if dist <= NODE_RADIUS + 2:
                return node["id"]
        return None

    def _get_edge_at(self, x: float, y: float) -> Optional[str]:
        """Find edge ID under mouse (distance to line segment)."""
        for edge in self.edges:
            n1 = next(n for n in self.nodes if n["id"] == edge["from"])
            n2 = next(n for n in self.nodes if n["id"] == edge["to"])
            x1, y1 = self._world_to_screen(n1["pos"])
            x2, y2 = self._world_to_screen(n2["pos"])
            
            # Distance from point to segment
            px, py = x2 - x1, y2 - y1
            norm = px*px + py*py
            if norm == 0: continue
            u =  ((x - x1) * px + (y - y1) * py) / float(norm)
            
            if u > 1: u = 1
            elif u < 0: u = 0
            
            dx = x1 + u * px
            dy = y1 + u * py
            
            dist = math.hypot(dx - x, dy - y)
            if dist < 5: # Tolerance
                return edge["id"]
        return None

    def _on_click(self, event: tk.Event) -> None:
        x, y = event.x, event.y
        
        if self.current_tool == TOOL_SELECT:
            # Try select node
            node_id = self._get_node_at(x, y)
            if node_id:
                self.selected_item = node_id
                self.drag_data["item"] = node_id
                self.drag_data["x"] = x
                self.drag_data["y"] = y
                self._redraw()
                return
            
            # Try select edge
            edge_id = self._get_edge_at(x, y)
            if edge_id:
                self.selected_item = edge_id
                self._redraw()
                return
                
            self.selected_item = None
            self._redraw()

        elif self.current_tool in (TOOL_ROOM, TOOL_TOILET, TOOL_ENTRANCE, TOOL_JUNCTION):
            self._add_node(x, y, self.current_tool)

        elif self.current_tool in (TOOL_CONNECT, TOOL_CONNECT_DIRECTED):
            node_id = self._get_node_at(x, y)
            if node_id:
                if self.connection_start is None:
                    self.connection_start = node_id
                    self._redraw() # Highlight start
                else:
                    if node_id != self.connection_start:
                        is_oneway = (self.current_tool == TOOL_CONNECT_DIRECTED)
                        self._add_edge(self.connection_start, node_id, oneway=is_oneway)
                    self.connection_start = None
                    self._redraw()

        elif self.current_tool == TOOL_ONEWAY:
            edge_id = self._get_edge_at(x, y)
            if edge_id:
                self._toggle_oneway(edge_id)

        elif self.current_tool == TOOL_DELETE:
            node_id = self._get_node_at(x, y)
            if node_id:
                self._delete_node(node_id)
                return
            edge_id = self._get_edge_at(x, y)
            if edge_id:
                self._delete_edge(edge_id)

    def _on_drag(self, event: tk.Event) -> None:
        if self.current_tool == TOOL_SELECT and self.drag_data["item"]:
            node_id = self.drag_data["item"]
            # Update position
            wx, wy = self._screen_to_world(event.x, event.y)
            
            for node in self.nodes:
                if node["id"] == node_id:
                    node["pos"] = [wx, wy, 0.0]
                    break
            self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        self.drag_data["item"] = None

    # --- Loading & Resetting ---

    def clear_and_reset(self) -> None:
        """Reset editor to blank state."""
        self.nodes = []
        self.edges = []
        self.next_id = 1
        self._redraw()

    def load_from_floorplan(self, plan: Any) -> None:
        """Load an existing FloorPlan object into the editor."""
        self.nodes = []
        self.edges = []
        
        # Convert nodes
        max_id_num = 0
        for node in plan.nodes:
            # Extract numeric part of ID if possible for next_id
            try:
                num = int(''.join(filter(str.isdigit, node.node_id)))
                max_id_num = max(max_id_num, num)
            except ValueError:
                pass
                
            n_dict = {
                "id": node.node_id,
                "label": node.label,
                "type": node.kind,
                "floor": node.floor,
                "pos": list(node.position),
                "is_entrance": node.metadata.get("is_entrance", False) if node.metadata else False
            }
            self.nodes.append(n_dict)
            
        # Convert edges
        for edge in plan.edges:
            try:
                num = int(''.join(filter(str.isdigit, edge.edge_id)))
                max_id_num = max(max_id_num, num)
            except ValueError:
                pass
                
            e_dict = {
                "id": edge.edge_id,
                "from": edge.source,
                "to": edge.target,
                "length_m": edge.length_m,
                "width_m": edge.width_m,
                "capacity_pps": edge.capacity_pps,
                "oneway": edge.metadata.get("oneway", False) if edge.metadata else False
            }
            self.edges.append(e_dict)
            
        self.next_id = max_id_num + 1
        self._redraw()

    # --- Logic ---

    def _add_node(self, sx: float, sy: float, tool_type: str) -> None:
        wx, wy = self._screen_to_world(sx, sy)
        kind_map = {
            TOOL_ROOM: "room",
            TOOL_TOILET: "toilet",
            TOOL_ENTRANCE: "junction", # Entrance is just a junction logically, but we label it
            TOOL_JUNCTION: "junction"
        }
        
        kind = kind_map[tool_type]
        label = ""
        if tool_type == TOOL_ROOM:
            label = f"R{self.next_id}"
        elif tool_type == TOOL_TOILET:
            label = "WC"
        elif tool_type == TOOL_ENTRANCE:
            label = "ENTRY"
            
        node = {
            "id": f"n_{self.next_id}",
            "label": label,
            "type": kind,
            "floor": 0,
            "pos": [wx, wy, 0.0]
        }
        
        # Special metadata for entrance
        if tool_type == TOOL_ENTRANCE:
            node["is_entrance"] = True
            
        self.nodes.append(node)
        self.next_id += 1
        self._redraw()

    def _add_edge(self, u: str, v: str, oneway: bool = False) -> None:
        # Check if exists
        for e in self.edges:
            if (e["from"] == u and e["to"] == v) or (e["from"] == v and e["to"] == u):
                return
        
        edge = {
            "id": f"e_{self.next_id}",
            "from": u,
            "to": v,
            "length_m": 10.0, # Placeholder, should calc from dist
            "width_m": 2.0,
            "capacity_pps": 1.5,
            "oneway": oneway
        }
        # Auto-calc length
        n1 = next(n for n in self.nodes if n["id"] == u)
        n2 = next(n for n in self.nodes if n["id"] == v)
        dist = math.hypot(n1["pos"][0] - n2["pos"][0], n1["pos"][1] - n2["pos"][1])
        edge["length_m"] = round(dist, 1)
        
        self.edges.append(edge)
        self.next_id += 1
        self._redraw()

    def _toggle_oneway(self, edge_id: str) -> None:
        for edge in self.edges:
            if edge["id"] == edge_id:
                # Cycle: 2-Way -> 1-Way (Forward) -> 1-Way (Reverse) -> 2-Way
                if not edge.get("oneway"):
                    # 2-Way -> 1-Way (Forward)
                    edge["oneway"] = True
                else:
                    # Was 1-Way. Check if we should flip or go back to 2-Way.
                    # We can use a temporary flag or just check if we just flipped?
                    # Let's assume: If 1-Way, flip direction. If flipped, go to 2-Way?
                    # That requires state.
                    # Simpler: Just flip direction. To go back to 2-Way, maybe right click?
                    # Or: 1-Way (Forward) -> 1-Way (Reverse) -> 2-Way
                    
                    # We need to know if it was "Forward" or "Reverse" relative to original creation?
                    # No, just swap nodes to reverse.
                    
                    # But how do we know if we should go to 2-Way next?
                    # Let's add a "reversed" flag? No.
                    
                    # Let's try:
                    # If oneway=True, we flip direction (swap nodes).
                    # BUT, if we keep doing that, we never go back to 2-Way.
                    
                    # Let's use a metadata tag "flip_state" just for the editor session?
                    # Or just: 
                    # If oneway=True:
                    #    Ask user? No.
                    #    Let's just make it: Toggle = Switch between 2-Way and 1-Way.
                    #    To Flip, maybe hold Shift? Or just re-draw?
                    #    Actually, the user asked for "Toggle/Flip".
                    
                    # Let's implement: 2-Way -> 1-Way -> Flip -> 2-Way
                    # We can detect "Flip" by checking if we just swapped? No.
                    
                    # Let's add a property "state": 0=2way, 1=1way, 2=1way_rev
                    state = edge.get("_edit_state", 0)
                    state = (state + 1) % 3
                    edge["_edit_state"] = state
                    
                    if state == 0:
                        edge["oneway"] = False
                    elif state == 1:
                        edge["oneway"] = True
                        # Ensure original direction (if we swapped before, swap back?)
                        # This is getting complex.
                        
                        # Simple approach:
                        # If 2-Way -> Make 1-Way (Forward)
                        # If 1-Way -> Flip Direction (Swap nodes)
                        # If 1-Way (and user wants 2-way) -> They have to cycle?
                        # Let's just do: 2-Way -> 1-Way -> Flip -> 2-Way
                        pass
                    
                    # Let's try a simpler logic without hidden state:
                    # If 2-Way -> 1-Way
                    # If 1-Way -> Flip Direction (Swap nodes) AND stay 1-Way? 
                    #    Wait, if I click again, I want 2-Way?
                    #    How to distinguish "Flip" from "Disable"?
                    
                    # Let's use the "oneway" flag + a check.
                    # If oneway is True:
                    #   If we haven't flipped yet (how do we know? we don't).
                    #   Let's just do: 2-Way -> 1-Way -> 2-Way.
                    #   AND add a separate "Flip" logic?
                    #   Or: 2-Way -> 1-Way -> Flip -> 2-Way.
                    
                    # To implement "Flip -> 2-Way", we need to know we are in "Flip" state.
                    # Let's just use a counter on the edge object in memory.
                    
                    cycle = edge.get("_cycle", 0)
                    cycle = (cycle + 1) % 3
                    edge["_cycle"] = cycle
                    
                    if cycle == 0: # 2-Way
                        edge["oneway"] = False
                    elif cycle == 1: # 1-Way Forward
                        edge["oneway"] = True
                    elif cycle == 2: # 1-Way Reverse
                        edge["oneway"] = True
                        edge["from"], edge["to"] = edge["to"], edge["from"]
                        
                break
        self._redraw()

    def _delete_node(self, node_id: str) -> None:
        self.nodes = [n for n in self.nodes if n["id"] != node_id]
        self.edges = [e for e in self.edges if e["from"] != node_id and e["to"] != node_id]
        self._redraw()

    def _delete_edge(self, edge_id: str) -> None:
        self.edges = [e for e in self.edges if e["id"] != edge_id]
        self._redraw()

    def _clear_canvas(self) -> None:
        if messagebox.askyesno("Confirm", "Clear entire drawing?"):
            self.nodes = []
            self.edges = []
            self.next_id = 1
            self._redraw()

    # --- Drawing ---

    def _screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        return (sx / SCALE_PX_PER_M, sy / SCALE_PX_PER_M)

    def _world_to_screen(self, pos: List[float]) -> Tuple[float, float]:
        return (pos[0] * SCALE_PX_PER_M, pos[1] * SCALE_PX_PER_M)

    def _redraw(self) -> None:
        self.canvas.delete("all")
        
        # Draw Edges
        for edge in self.edges:
            n1 = next(n for n in self.nodes if n["id"] == edge["from"])
            n2 = next(n for n in self.nodes if n["id"] == edge["to"])
            x1, y1 = self._world_to_screen(n1["pos"])
            x2, y2 = self._world_to_screen(n2["pos"])
            
            color = "#cccccc" # Light gray
            width = 2
            
            if edge.get("oneway"):
                color = "#ff4444" # Brighter red
            
            if self.selected_item == edge["id"]:
                color = SELECTION_COLOR
                width = 3
                
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width)
            
            # Draw arrow in middle if one-way
            if edge.get("oneway"):
                # Calculate midpoint
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                
                # Calculate angle
                dx, dy = x2 - x1, y2 - y1
                angle = math.atan2(dy, dx)
                
                # Arrow size
                size = 12
                
                # Tip
                tip_x = mx + (size/2) * math.cos(angle)
                tip_y = my + (size/2) * math.sin(angle)
                
                # Wings
                wing_angle = 0.5 # radians (~30 degrees)
                
                w1_x = tip_x - size * math.cos(angle - wing_angle)
                w1_y = tip_y - size * math.sin(angle - wing_angle)
                
                w2_x = tip_x - size * math.cos(angle + wing_angle)
                w2_y = tip_y - size * math.sin(angle + wing_angle)
                
                self.canvas.create_polygon(tip_x, tip_y, w1_x, w1_y, w2_x, w2_y, fill=color)

        # Draw Nodes
        for node in self.nodes:
            x, y = self._world_to_screen(node["pos"])
            
            kind = node["type"]
            color = "gray"
            radius = NODE_RADIUS
            
            if kind == "room": color = "#D32F2F" # Red
            elif kind == "toilet": color = "#7B1FA2" # Purple
            elif node.get("is_entrance"): color = "#388E3C" # Green
            
            if self.selected_item == node["id"]:
                self.canvas.create_oval(x-radius-3, y-radius-3, x+radius+3, y+radius+3, outline=SELECTION_COLOR, width=2)
                
            if self.connection_start == node["id"]:
                self.canvas.create_oval(x-radius-3, y-radius-3, x+radius+3, y+radius+3, outline="orange", width=2)

            self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=color, outline="black")
            
            if node["label"]:
                self.canvas.create_text(x, y-radius-10, text=node["label"], font=("Arial", 8), fill="#ffffff")

    # --- Saving ---

    def _save_project(self) -> None:
        if not self.nodes:
            messagebox.showwarning("Empty", "Nothing to save!")
            return
            
        # 1. Save Floorplan
        fp_data = {
            "nodes": self.nodes,
            "edges": self.edges
        }
        
        filename = filedialog.asksaveasfilename(
            title="Save Layout",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialdir=Path.cwd() / "data" / "samples"
        )
        
        if not filename:
            return
            
        try:
            with open(filename, "w") as f:
                json.dump(fp_data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save layout: {e}")
            return

        # 2. Generate Scenario
        # Ask user for scenario type
        # We'll use a simple dialog or just assume "Full Day" if they say Yes to generation.
        # Let's make it a Yes/No for "Generate Scenario?" and then if Yes, we do a comprehensive one.
        
        if not messagebox.askyesno("Generate Scenario", "Do you want to generate a simulation scenario for this layout?"):
            # Just save layout and exit
            self._finish_save(filename)
            return

        self._generate_scenario(filename)

    def _finish_save(self, layout_path: str) -> None:
        # Auto-load into app
        self.controller.state["floorplan_path"] = Path(layout_path)
        
        # Explicitly load the floorplan object now to ensure sync
        from smartflow.core.floorplan import load_floorplan
        try:
            plan = load_floorplan(Path(layout_path))
            self.controller.state["floorplan"] = plan
            
            # Navigate back to LayoutView to show the loaded nodes
            self.controller.show_frame("LayoutView")
            
        except Exception as e:
            print(f"Warning: Failed to auto-load floorplan: {e}")
            messagebox.showwarning("Warning", f"Saved, but failed to auto-load: {e}")

    def _generate_scenario(self, layout_path: str) -> None:
        import random
        
        # Identify nodes
        entrances = [n["id"] for n in self.nodes if n.get("is_entrance")]
        rooms = [n["id"] for n in self.nodes if n["type"] == "room"]
        
        if not rooms:
            messagebox.showwarning("Warning", "No Room nodes found! Cannot generate scenario.")
            self._finish_save(layout_path)
            return

        periods = []
        
        # --- Period 1: Morning Arrival (08:30) ---
        # Entrance -> Random Rooms
        if entrances:
            movements_p1 = []
            total_students = 100
            
            # Distribute students randomly among rooms
            # Each student picks a random room
            # To represent this in "movements" (which are flows), we create a flow for each room.
            
            # Assign counts
            counts = {r: 0 for r in rooms}
            for _ in range(total_students):
                r = random.choice(rooms)
                counts[r] += 1
                
            for room, count in counts.items():
                if count > 0:
                    movements_p1.append({
                        "population": "student",
                        "count": count,
                        "origin": entrances[0], # Main entrance
                        "destination": room
                    })
            
            periods.append({
                "id": "morning_arrival",
                "start_time": "08:30",
                "movements": movements_p1
            })

        # --- Period 2: Lesson Change (08:35) ---
        # We set this to 5 minutes later so it runs in the same simulation session
        # without waiting for an hour of simulated time.
        
        # Room -> Random Other Room
        movements_p2 = []
        
        # Assume ~20 students per room need to move
        students_per_room = 20
        
        for origin in rooms:
            # Where do these 20 students go?
            # They split up into small groups going to different rooms.
            # e.g. 3 go to Room A, 5 go to Room B...
            
            # Pick 3-5 random destinations (excluding self)
            possible_dests = [r for r in rooms if r != origin]
            if not possible_dests:
                continue
                
            # Randomly decide how many destinations this room feeds into
            num_dests = min(len(possible_dests), random.randint(2, 4))
            targets = random.sample(possible_dests, num_dests)
            
            # Distribute the 20 students among these targets
            remaining = students_per_room
            for i, target in enumerate(targets):
                if i == len(targets) - 1:
                    count = remaining # Last one takes the rest
                else:
                    # Random chunk
                    count = random.randint(1, remaining - (len(targets) - i - 1))
                
                remaining -= count
                
                if count > 0:
                    movements_p2.append({
                        "population": "student",
                        "count": count,
                        "origin": origin,
                        "destination": target
                    })
                    
        periods.append({
            "id": "lesson_change",
            "start_time": "08:35",
            "movements": movements_p2
        })

        scenario_data = {
            "random_seed": 42,
            "tick_seconds": 0.5,
            "transition_window_s": 600, # 10 minutes covers both periods (08:30-08:40)
            "periods": periods,
            "behaviour": {
                "speed_base_mps": {"distribution": "normal", "mean": 1.4, "std": 0.2},
                "depart_jitter_s": {"uniform": [0, 60]} # Spread departures over a minute
            }
        }
        
        scen_path = Path(layout_path).with_name(Path(layout_path).stem + "_scenario.json")
        try:
            with open(scen_path, "w") as f:
                json.dump(scenario_data, f, indent=2)
            messagebox.showinfo("Success", f"Saved layout and generated Full Day scenario!\n\nScenario: {scen_path.name}")
            self._finish_save(layout_path)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save scenario: {e}")
            self._finish_save(layout_path)
