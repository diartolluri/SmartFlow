"""
Interactive Floor Plan Editor.
Allows users to draw nodes and edges, configure properties, and save to JSON.
"""

from __future__ import annotations

import copy
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
TOOL_STAIRS = "stairs"
TOOL_NODE = "node"
TOOL_CANTEEN = "canteen"
TOOL_SEATING = "seating_area"

SUBJECT_OPTIONS = [
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
]

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
        
        # Phase 3: Multi-Floor State
        self.current_floor = 0
        self.show_ghosting = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        
        # Undo/Redo Stacks
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.pre_drag_state: Optional[Dict[str, Any]] = None
        self.drag_occurred = False
        
        # Viewport State
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        
        self._init_ui()

    def _init_ui(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # Tools
        tools_frame = ttk.LabelFrame(toolbar, text="Tools", padding=5)
        tools_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        self.tool_var = tk.StringVar(value=TOOL_SELECT)
        
        tools = [
            (TOOL_SELECT, "Select/Move"),
            (TOOL_ROOM, "Add Room"),
            (TOOL_TOILET, "Add Toilet"),
            (TOOL_CANTEEN, "Add Canteen"),
            (TOOL_SEATING, "Add Seating Area"),
            (TOOL_ENTRANCE, "Add Entrance"),
            (TOOL_JUNCTION, "Add Junction"),
            (TOOL_STAIRS, "Add Stairs"),
            (TOOL_CONNECT, "Connect (2-way)"),
            (TOOL_CONNECT_DIRECTED, "Connect (1-way)"),
            (TOOL_DELETE, "Delete")
        ]
        
        for val, label in tools:
            rb = ttk.Radiobutton(
                tools_frame, 
                text=label, 
                value=val, 
                variable=self.tool_var,
                command=self._on_tool_change
            )
            rb.pack(anchor=tk.W)

        # Floor Controls
        floor_frame = ttk.LabelFrame(toolbar, text="Floor Control", padding=5)
        floor_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Label(floor_frame, text="Current Floor:").pack(anchor=tk.W)
        self.floor_combo = ttk.Combobox(floor_frame, values=["0", "1", "2", "3"], state="readonly", width=5)
        self.floor_combo.set("0")
        self.floor_combo.pack(anchor=tk.W, pady=2)
        self.floor_combo.bind("<<ComboboxSelected>>", self._on_floor_change)

        ttk.Checkbutton(floor_frame, text="Ghosting", variable=self.show_ghosting, command=self._redraw).pack(anchor=tk.W, pady=5)

        # Display options
        ttk.Checkbutton(floor_frame, text="Grid (5m)", variable=self.show_grid, command=self._redraw).pack(anchor=tk.W)

        # Actions
        actions_frame = ttk.LabelFrame(toolbar, text="Actions", padding=5)
        actions_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Button(actions_frame, text="Clear", command=self._clear_canvas).pack(fill=tk.X, pady=2)
        ttk.Button(actions_frame, text="Save", command=self._save_project).pack(fill=tk.X, pady=2)
        ttk.Button(actions_frame, text="Back", command=self._go_back).pack(fill=tk.X, pady=2)
            
        # Properties Panel
        # (Existing properties panel code here...)

        # Canvas Container with Scrollbars
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#1e1e1e", cursor="arrow", highlightthickness=0)
        
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Events
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        
        # Pan/Zoom Bindings
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)
        
        # Undo/Redo Bindings
        self.controller.bind("<Control-z>", self._undo)
        self.controller.bind("<Control-y>", self._redo)
        self.controller.bind("<Control-s>", self._save_project_shortcut)

    def _on_tool_change(self) -> None:
        """Handle tool selection change."""
        self.current_tool = self.tool_var.get()
        self.connection_start = None
        self._redraw()

    def _on_floor_change(self, event=None) -> None:
        """Handle floor selection change."""
        try:
            self.current_floor = int(self.floor_combo.get())
            self._redraw()
        except ValueError:
            pass

    # --- Undo/Redo Logic ---

    def _save_state(self) -> None:
        """Push current state to undo stack."""
        state = {
            "nodes": copy.deepcopy(self.nodes),
            "edges": copy.deepcopy(self.edges),
            "next_id": self.next_id
        }
        self.undo_stack.append(state)
        self.redo_stack.clear() # New action clears redo history
        
        # Limit stack size
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def _undo(self, event: tk.Event = None) -> None:
        """Revert to previous state."""
        if not self.undo_stack:
            return
            
        # Save current state to redo stack
        current_state = {
            "nodes": copy.deepcopy(self.nodes),
            "edges": copy.deepcopy(self.edges),
            "next_id": self.next_id
        }
        self.redo_stack.append(current_state)
        
        # Restore previous state
        prev_state = self.undo_stack.pop()
        self.nodes = prev_state["nodes"]
        self.edges = prev_state["edges"]
        self.next_id = prev_state["next_id"]
        
        self.selected_item = None
        self._redraw()

    def _redo(self, event: tk.Event = None) -> None:
        """Reapply reverted state."""
        if not self.redo_stack:
            return
            
        # Save current state to undo stack
        current_state = {
            "nodes": copy.deepcopy(self.nodes),
            "edges": copy.deepcopy(self.edges),
            "next_id": self.next_id
        }
        self.undo_stack.append(current_state)
        
        # Restore next state
        next_state = self.redo_stack.pop()
        self.nodes = next_state["nodes"]
        self.edges = next_state["edges"]
        self.next_id = next_state["next_id"]
        
        self.selected_item = None
        self._redraw()

    def _get_node_at(self, x: float, y: float) -> Optional[str]:
        """Find node ID under mouse."""
        # Simple hit testing
        for node in self.nodes:
            if node.get("floor", 0) != self.current_floor:
                continue
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
            
            # Filter by floor: Show if either node is on current floor
            f1 = n1.get("floor", 0)
            f2 = n2.get("floor", 0)
            if f1 != self.current_floor and f2 != self.current_floor:
                continue
                
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


    def _on_double_click(self, event: tk.Event) -> None:
        """Handle double click for property editing."""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        
        edge_id = self._get_edge_at(x, y)
        if edge_id:
            self._edit_edge_properties(edge_id)
            return
            
        node_id = self._get_node_at(x, y)
        if node_id:
            self._edit_node_properties(node_id)

    def _edit_edge_properties(self, edge_id: str) -> None:
        edge = next(e for e in self.edges if e["id"] == edge_id)
        
        # Ask for new width (interpreted as "people-wide" in the UI)
        new_width = simpledialog.askfloat(
            "Edge Properties", 
            f"Enter width for edge {edge_id} (people wide):",
            initialvalue=edge.get("width_m", 3.0),
            minvalue=1.0,
            maxvalue=12.0
        )
        
        if new_width is not None:
            self._save_state()
            edge["width_m"] = new_width
            self._redraw()

    def _edit_node_properties(self, node_id: str) -> None:
        node = next(n for n in self.nodes if n["id"] == node_id)

        win = tk.Toplevel(self)
        win.title(f"Node Properties: {node_id}")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())

        container = ttk.Frame(win, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        label_var = tk.StringVar(value=str(node.get("label", "")))
        capacity_var = tk.StringVar(value=str(int(node.get("capacity", 1000))))
        subject_var = tk.StringVar(value=str(node.get("subject", "other")))

        row = 0
        ttk.Label(container, text="Label:").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(container, textvariable=label_var, width=24).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(container, text="Capacity (people):").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(container, textvariable=capacity_var, width=24).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        is_room = str(node.get("type", "")).lower() == "room"
        if is_room:
            ttk.Label(container, text="Subject:").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            subject_combo = ttk.Combobox(container, values=SUBJECT_OPTIONS, state="readonly", textvariable=subject_var, width=22)
            if subject_var.get() not in SUBJECT_OPTIONS:
                subject_var.set("other")
            subject_combo.grid(row=row, column=1, sticky="ew", pady=4)
            row += 1

        container.grid_columnconfigure(1, weight=1)

        btns = ttk.Frame(container)
        btns.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))

        result = {"ok": False}

        def on_ok() -> None:
            # Validate
            try:
                cap = int(str(capacity_var.get()).strip())
            except Exception:
                messagebox.showerror("Invalid value", "Capacity must be an integer.", parent=win)
                return
            if cap < 1 or cap > 10000:
                messagebox.showerror("Invalid value", "Capacity must be between 1 and 10000.", parent=win)
                return

            subj = str(subject_var.get()).strip().lower()
            if is_room and subj not in SUBJECT_OPTIONS:
                subj = "other"

            self._save_state()
            node["label"] = str(label_var.get())
            node["capacity"] = cap
            if is_room:
                node["subject"] = subj

            result["ok"] = True
            win.destroy()

        def on_cancel() -> None:
            win.destroy()

        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=(0, 8))

        win.grab_set()
        win.wait_window()

        if result["ok"]:
            self._redraw()

    def _on_click(self, event: tk.Event) -> None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        self.drag_occurred = False
        
        if self.current_tool == TOOL_SELECT:
            # Try select node
            node_id = self._get_node_at(x, y)
            if node_id:
                self.selected_item = node_id
                self.drag_data["item"] = node_id
                self.drag_data["x"] = x
                self.drag_data["y"] = y
                
                # Capture state before potential drag
                self.pre_drag_state = {
                    "nodes": copy.deepcopy(self.nodes),
                    "edges": copy.deepcopy(self.edges),
                    "next_id": self.next_id
                }
                
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

        elif self.current_tool in (TOOL_ROOM, TOOL_TOILET, TOOL_ENTRANCE, TOOL_JUNCTION, TOOL_STAIRS):
            self._save_state()
            self._add_node(x, y, self.current_tool)

        elif self.current_tool in (TOOL_CONNECT, TOOL_CONNECT_DIRECTED):
            node_id = self._get_node_at(x, y)
            if node_id:
                if self.connection_start is None:
                    self.connection_start = node_id
                    self._redraw() # Highlight start
                else:
                    if node_id != self.connection_start:
                        self._save_state()
                        is_oneway = (self.current_tool == TOOL_CONNECT_DIRECTED)
                        self._add_edge(self.connection_start, node_id, oneway=is_oneway)
                    self.connection_start = None
                    self._redraw()

        elif self.current_tool == TOOL_ONEWAY:
            edge_id = self._get_edge_at(x, y)
            if edge_id:
                self._save_state()
                self._toggle_oneway(edge_id)

        elif self.current_tool == TOOL_DELETE:
            node_id = self._get_node_at(x, y)
            if node_id:
                self._save_state()
                self._delete_node(node_id)
                return
            edge_id = self._get_edge_at(x, y)
            if edge_id:
                self._save_state()
                self._delete_edge(edge_id)

    def _on_drag(self, event: tk.Event) -> None:
        # Auto-scroll if near edges
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        scroll_margin = 20
        
        if event.x > w - scroll_margin:
            self.canvas.xview_scroll(1, "units")
        elif event.x < scroll_margin:
            self.canvas.xview_scroll(-1, "units")
            
        if event.y > h - scroll_margin:
            self.canvas.yview_scroll(1, "units")
        elif event.y < scroll_margin:
            self.canvas.yview_scroll(-1, "units")

        if self.current_tool == TOOL_SELECT and self.drag_data["item"]:
            self.drag_occurred = True
            node_id = self.drag_data["item"]
            # Update position
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            wx, wy = self._screen_to_world(cx, cy)
            
            for node in self.nodes:
                if node["id"] == node_id:
                    # Preserve Z if it exists
                    old_z = node["pos"][2] if len(node["pos"]) > 2 else 0.0
                    node["pos"] = [wx, wy, old_z]
                    break
            self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        if self.drag_occurred and self.pre_drag_state:
            self.undo_stack.append(self.pre_drag_state)
            self.redo_stack.clear()
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
                
        self.drag_data["item"] = None
        self.pre_drag_state = None
        self.drag_occurred = False

    # --- Loading & Resetting ---

    def clear_and_reset(self) -> None:
        """Reset editor to blank state."""
        self.nodes = []
        self.edges = []
        self.next_id = 1
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._redraw()

    def load_from_floorplan(self, plan: Any) -> None:
        """Load an existing FloorPlan object into the editor."""
        self.nodes = []
        self.edges = []
        self.undo_stack.clear()
        self.redo_stack.clear()
        
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
                "capacity": getattr(node, "capacity", 1000),
                "is_entrance": node.metadata.get("is_entrance", False) if node.metadata else False,
                "subject": (node.metadata.get("subject") if node.metadata else None),
            }
            if not n_dict.get("subject"):
                n_dict["subject"] = "other"
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
        
        kind = "room"
        label_prefix = "N"
        default_label = "NODE"
        is_entrance = False
        capacity = 1000  # Default high capacity
        
        if tool_type == TOOL_ROOM:
            kind = "room"
            label_prefix = "R"
            default_label = ""
        elif tool_type == TOOL_TOILET:
            kind = "toilet"
            label_prefix = "WC"
            default_label = ""
        elif tool_type == TOOL_CANTEEN:
            kind = "canteen"
            label_prefix = "CAN"
            default_label = ""
            # Prompt for canteen capacity
            cap_str = simpledialog.askstring(
                "Canteen Capacity",
                "Enter maximum seating capacity:",
                initialvalue="200"
            )
            if cap_str:
                try:
                    capacity = max(1, int(cap_str))
                except ValueError:
                    capacity = 200
            else:
                return  # User cancelled
        elif tool_type == TOOL_SEATING:
            kind = "seating_area"
            label_prefix = "SA"
            default_label = ""
            # Prompt for seating area capacity
            cap_str = simpledialog.askstring(
                "Seating Area Capacity",
                "Enter maximum occupancy:",
                initialvalue="50"
            )
            if cap_str:
                try:
                    capacity = max(1, int(cap_str))
                except ValueError:
                    capacity = 50
            else:
                return  # User cancelled
        elif tool_type == TOOL_ENTRANCE:
            kind = "junction"
            label_prefix = "E"
            is_entrance = True
            default_label = ""
        elif tool_type == TOOL_JUNCTION:
            kind = "junction"
            label_prefix = "J"
            default_label = ""
        elif tool_type == TOOL_STAIRS:
            kind = "stairs"
            label_prefix = "ST"
            default_label = ""
            
        node_id = f"{label_prefix}{self.next_id}"
        
        node = {
            "id": node_id,
            "label": default_label,
            "type": kind,
            "floor": self.current_floor,
            "pos": [wx, wy, 0.0],
            "capacity": capacity,
            "is_entrance": is_entrance,
            # Rooms can be assigned a subject; used in the key and scenario generation.
            "subject": ("canteen" if kind == "canteen" else ("other" if kind == "room" else "other")),
        }
        self.nodes.append(node)
        self.next_id += 1
        self._redraw()

        # Auto-connect stairs logic
        if tool_type == TOOL_STAIRS and self.current_floor > 0:
            if messagebox.askyesno("Stairwell", f"Create connecting stair on Floor {self.current_floor - 1}?"):
                prev_floor = self.current_floor - 1
                
                # Create matching node on previous floor
                other_node_id = f"ST{self.next_id}"
                other_node = {
                    "id": other_node_id,
                    "label": "STAIRS",
                    "type": "stairs",
                    "floor": prev_floor,
                    "pos": [wx, wy, 0.0],
                    "capacity": 1000,
                    "is_entrance": False
                }
                self.nodes.append(other_node)
                self.next_id += 1
                
                # Create 2-way connection
                self._add_edge(node_id, other_node_id, oneway=False)

    def _add_edge(self, u: str, v: str, oneway: bool = False) -> None:
        # Check if exists
        for e in self.edges:
            if (e["from"] == u and e["to"] == v) or (e["from"] == v and e["to"] == u):
                return
        
        n1 = next(n for n in self.nodes if n["id"] == u)
        n2 = next(n for n in self.nodes if n["id"] == v)
        
        # Calculate distance
        dx = n1["pos"][0] - n2["pos"][0]
        dy = n1["pos"][1] - n2["pos"][1]
        
        f1 = n1.get("floor", 0)
        f2 = n2.get("floor", 0)
        
        length = 0.0
        width = 3.0
        
        if f1 != f2:
            # Stairwell connection
            # Assume 3.5m height per floor
            dz = (f2 - f1) * 3.5
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            width = 2.0 # Stairs are typically narrower than corridors
        else:
            length = math.hypot(dx, dy)
            width = 3.0
            
        edge = {
            "id": f"e_{self.next_id}",
            "from": u,
            "to": v,
            "length_m": round(length, 1),
            "width_m": width,
            "capacity_pps": 1.5,
            "oneway": oneway
        }
        
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
                        # If 1-Way (and user wants 2-way) -> they have to cycle?
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

    def _on_zoom(self, event: tk.Event) -> None:
        """Handle mouse wheel zoom."""
        # Zoom factor
        factor = 1.1 if event.delta > 0 else 0.9
        
        # Calculate new scale
        new_scale = self.scale * factor
        
        # Limit zoom
        if new_scale < 0.1 or new_scale > 10.0:
            return
            
        # Zoom centered on mouse cursor
        # 1. Convert mouse screen pos to world pos (using OLD scale)
        wx, wy = self._screen_to_world(event.x, event.y)
        
        # 2. Update scale
        self.scale = new_scale
        
        # 3. Adjust offset so that world pos (wx, wy) is still at screen pos (event.x, event.y)
        # screen_x = (world_x * SCALE * scale) + offset_x
        # offset_x = screen_x - (world_x * SCALE * scale)
        self.offset_x = event.x - (wx * SCALE_PX_PER_M * self.scale)
        self.offset_y = event.y - (wy * SCALE_PX_PER_M * self.scale)
        
        self._redraw()

    def _on_pan_start(self, event: tk.Event) -> None:
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def _on_pan_drag(self, event: tk.Event) -> None:
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        
        self.offset_x += dx
        self.offset_y += dy
        
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        
        self._redraw()

    def _screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        # screen = (world * SCALE * scale) + offset
        # world = (screen - offset) / (SCALE * scale)
        return (
            (sx - self.offset_x) / (SCALE_PX_PER_M * self.scale),
            (sy - self.offset_y) / (SCALE_PX_PER_M * self.scale)
        )

    def _world_to_screen(self, pos: List[float]) -> Tuple[float, float]:
        return (
            (pos[0] * SCALE_PX_PER_M * self.scale) + self.offset_x,
            (pos[1] * SCALE_PX_PER_M * self.scale) + self.offset_y
        )

    def _redraw(self) -> None:
        self.canvas.delete("all")

        # --- Grid (draw first so it sits behind everything) ---
        if bool(self.show_grid.get()):
            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 600

            # Visible screen bounds in canvas coordinates
            sx0 = self.canvas.canvasx(0)
            sy0 = self.canvas.canvasy(0)
            sx1 = self.canvas.canvasx(cw)
            sy1 = self.canvas.canvasy(ch)

            # Convert to world bounds
            wx0, wy0 = self._screen_to_world(sx0, sy0)
            wx1, wy1 = self._screen_to_world(sx1, sy1)
            min_wx, max_wx = (min(wx0, wx1), max(wx0, wx1))
            min_wy, max_wy = (min(wy0, wy1), max(wy0, wy1))

            grid_m = 5.0
            start_x = math.floor(min_wx / grid_m) * grid_m
            end_x = math.ceil(max_wx / grid_m) * grid_m
            start_y = math.floor(min_wy / grid_m) * grid_m
            end_y = math.ceil(max_wy / grid_m) * grid_m

            grid_color = "#2a2a2a"
            # Keep grid subtle; dash scales with zoom so it remains readable
            dash = (2, 6)

            x = start_x
            while x <= end_x + 1e-9:
                x0, y0 = self._world_to_screen([x, start_y, 0.0])
                x1, y1 = self._world_to_screen([x, end_y, 0.0])
                self.canvas.create_line(x0, y0, x1, y1, fill=grid_color, dash=dash)
                x += grid_m

            y = start_y
            while y <= end_y + 1e-9:
                x0, y0 = self._world_to_screen([start_x, y, 0.0])
                x1, y1 = self._world_to_screen([end_x, y, 0.0])
                self.canvas.create_line(x0, y0, x1, y1, fill=grid_color, dash=dash)
                y += grid_m

        # Update scrollregion based on content
        min_x, min_y = 0, 0
        max_x, max_y = 1000, 800 # Default minimum size
        
        for node in self.nodes:
            sx, sy = self._world_to_screen(node["pos"])
            min_x = min(min_x, sx)
            min_y = min(min_y, sy)
            max_x = max(max_x, sx)
            max_y = max(max_y, sy)
            
        # Add padding
        pad = 100
        self.canvas.configure(scrollregion=(min_x - pad, min_y - pad, max_x + pad, max_y + pad))
        
        # Helper to draw a single layer
        def draw_layer(floor_idx: int, is_ghost: bool):
            alpha_color = "#333333" if is_ghost else None
            
            # Draw Edges
            for edge in self.edges:
                n1 = next(n for n in self.nodes if n["id"] == edge["from"])
                n2 = next(n for n in self.nodes if n["id"] == edge["to"])
                
                f1 = n1.get("floor", 0)
                f2 = n2.get("floor", 0)
                
                # Visibility check
                if is_ghost:
                    # Ghost shows other floors
                    if f1 == self.current_floor and f2 == self.current_floor:
                        continue
                    # Only show ghost if it's on the floor immediately below/above? 
                    # For now show all other floors as ghost
                    if f1 != floor_idx and f2 != floor_idx:
                        continue
                else:
                    # Active layer shows current floor
                    # Show if either node is on this floor
                    if f1 != self.current_floor and f2 != self.current_floor:
                        continue

                x1, y1 = self._world_to_screen(n1["pos"])
                x2, y2 = self._world_to_screen(n2["pos"])
                
                color = "#cccccc" # Light grey
                if is_ghost: color = "#444444"
                
                width = 2
                
                if not is_ghost:
                    if edge.get("oneway"):
                        color = "#ff4444" # Brighter red
                    
                    if self.selected_item == edge["id"]:
                        color = SELECTION_COLOR
                        width = 3
                
                # Calculate display width based on zoom
                # width_m * pixels_per_meter * zoom_scale
                px_per_m = SCALE_PX_PER_M * self.scale
                display_width = max(2, edge.get("width_m", 2.0) * px_per_m)

                if not is_ghost and self.selected_item == edge["id"]:
                    display_width += 2
                    
                self.canvas.create_line(x1, y1, x2, y2, fill=color, width=display_width)
                
                # Draw arrow (only for active layer)
                if not is_ghost and edge.get("oneway"):
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    dx, dy = x2 - x1, y2 - y1
                    angle = math.atan2(dy, dx)
                    size = 12
                    tip_x = mx + (size/2) * math.cos(angle)
                    tip_y = my + (size/2) * math.sin(angle)
                    wing_angle = 0.5
                    w1_x = tip_x - size * math.cos(angle - wing_angle)
                    w1_y = tip_y - size * math.sin(angle - wing_angle)
                    w2_x = tip_x - size * math.cos(angle + wing_angle)
                    w2_y = tip_y - size * math.sin(angle + wing_angle)
                    self.canvas.create_polygon(tip_x, tip_y, w1_x, w1_y, w2_x, w2_y, fill=color)

            # Draw Nodes
            for node in self.nodes:
                if node.get("floor", 0) != floor_idx:
                    continue
                    
                x, y = self._world_to_screen(node["pos"])
                
                kind = node["type"]
                color = "gray" # Default grey
                radius = NODE_RADIUS
                
                if is_ghost:
                    color = "#333333"
                    outline = "#555555"
                    # Still highlight connection start if it's this node
                    if self.connection_start == node["id"]:
                         self.canvas.create_oval(x-radius-3, y-radius-3, x+radius+3, y+radius+3, outline="orange", width=2)
                else:
                    outline = "black"
                    if kind == "room": color = "#D32F2F"
                    elif kind == "toilet": color = "#7B1FA2"
                    elif kind == "canteen": color = "#FF9800"  # Orange for canteen
                    elif kind == "seating_area": color = "#4CAF50"  # Green for seating area
                    elif kind == "stairs": color = "#FFD700" # Gold for stairs
                    elif node.get("is_entrance"): color = "#388E3C"
                    
                    if self.selected_item == node["id"]:
                        self.canvas.create_oval(x-radius-3, y-radius-3, x+radius+3, y+radius+3, outline=SELECTION_COLOR, width=2)
                        
                    if self.connection_start == node["id"]:
                        self.canvas.create_oval(x-radius-3, y-radius-3, x+radius+3, y+radius+3, outline="orange", width=2)

                self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=color, outline=outline)

                # No on-canvas labels (use colour key instead).

        # 1. Draw Ghost Layers (if enabled)
        if self.show_ghosting.get():
            # Draw all other floors
            # Ideally we only draw the one below or above?
            # Let's just draw all others for now, but maybe sorted?
            for f in range(4):
                if f != self.current_floor:
                    draw_layer(f, is_ghost=True)
                    
        # 2. Draw Active Layer
        draw_layer(self.current_floor, is_ghost=False)


    # --- Saving ---

    def _go_back(self) -> None:
        if messagebox.askyesno("Confirm", "Go back? Unsaved changes will be lost."):
            self.controller.show_frame("LayoutView")

    def _save_project_shortcut(self, event=None) -> None:
        """Handle Ctrl+S keyboard shortcut."""
        # Only respond if EditorView is currently visible
        try:
            if self.winfo_viewable():
                self._save_project()
        except Exception:
            pass

    def _save_project(self) -> None:
        if not self.nodes:
            messagebox.showwarning("Empty", "Nothing to save!")
            return
            
        # 1. Save Floorplan
        fp_data = {
            "nodes": self.nodes,
            "edges": self.edges
        }
        
        current_path = self.controller.state.get("floorplan_path")
        filename = None
        
        if current_path and Path(current_path).exists():
            # Ask user: Overwrite or Save As?
            choice = messagebox.askyesnocancel("Save Layout", f"Overwrite existing file?\n{Path(current_path).name}")
            if choice is None: # Cancel
                return
            elif choice: # Yes -> Overwrite
                filename = str(current_path)
            else: # No -> Save As
                filename = filedialog.asksaveasfilename(
                    title="Save Layout As",
                    defaultextension=".json",
                    filetypes=[("JSON Files", "*.json")],
                    initialdir=Path.cwd() / "data" / "samples"
                )
        else:
            # No existing file, always Save As
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
        room_subject = {n["id"]: str(n.get("subject", "other")).lower() for n in self.nodes if n.get("type") == "room"}
        
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
            origin_subject = room_subject.get(origin, "other")
            possible_dests = [r for r in rooms if r != origin and room_subject.get(r, "other") != origin_subject]
            if not possible_dests:
                # Fallback: if the layout is mostly one subject, allow any other room.
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
                "speed_base_mps": {"normal": {"mean": 1.35, "sigma": 0.15}},
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
