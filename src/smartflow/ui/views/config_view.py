"""View for configuring simulation parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from typing import TYPE_CHECKING
from pathlib import Path

from ...io.importers import load_scenario
from ...core.floorplan import EdgeSpec

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class ConfigView(ttk.Frame):
    """Frame for editing schedule and population settings."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        self.scenario_data = None
        self.edge_oneway_states = {} # Map edge_id -> bool
        
        self._init_ui()

    def update_view(self) -> None:
        """Refresh UI with data from controller state."""
        self._populate_edge_list()
        
        # Auto-load scenario if one exists for this floorplan
        floorplan_path = self.controller.state.get("floorplan_path")
        if floorplan_path:
            path_obj = Path(floorplan_path)
            # Look for [name]_scenario.json
            scen_path = path_obj.with_name(path_obj.stem + "_scenario.json")
            
            # Only auto-load if we haven't selected one manually yet, or if it matches the current layout
            current_file = self.file_path_var.get()
            
            if scen_path.exists():
                # If no file selected, OR if the selected file is the old version of this scenario
                if not current_file or Path(current_file).name == scen_path.name:
                    print(f"Auto-loading scenario: {scen_path}")
                    self.file_path_var.set(str(scen_path))
                    try:
                        data = load_scenario(scen_path)
                        self.scenario_data = data
                        
                        if "transition_window_s" in data:
                            self.duration_var.set(int(data["transition_window_s"]))
                        if "random_seed" in data:
                            self.seed_var.set(int(data["random_seed"]))
                    except Exception as e:
                        print(f"Failed to auto-load scenario: {e}")

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Step 2: Configuration", font=("Segoe UI", 16, "bold"))
        header.pack(pady=(0, 20))

        # Main content area with scrollbar
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left column: File & Params
        left_col = ttk.Frame(main_frame)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Scenario File Selection
        file_frame = ttk.LabelFrame(left_col, text="Scenario File (Optional)", padding=16)
        file_frame.pack(fill=tk.X, pady=10)
        
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(file_frame, text="Browse...", command=self._browse_file).pack(side=tk.RIGHT)

        # Form Frame
        form_frame = ttk.LabelFrame(left_col, text="Simulation Parameters", padding=16)
        form_frame.pack(fill=tk.X, pady=10)

        # Duration
        ttk.Label(form_frame, text="Duration (seconds):").grid(row=0, column=0, sticky="w", pady=5)
        self.duration_var = tk.IntVar(value=300)
        ttk.Entry(form_frame, textvariable=self.duration_var).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        # Random Seed
        ttk.Label(form_frame, text="Random Seed:").grid(row=1, column=0, sticky="w", pady=5)
        self.seed_var = tk.IntVar(value=42)
        ttk.Entry(form_frame, textvariable=self.seed_var).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Population Scale (Optional)
        ttk.Label(form_frame, text="Population Scale:").grid(row=2, column=0, sticky="w", pady=5)
        self.scale_var = tk.DoubleVar(value=1.0)
        ttk.Entry(form_frame, textvariable=self.scale_var).grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        # Route Optimality (Beta)
        ttk.Label(form_frame, text="Route Optimality (Beta):").grid(row=3, column=0, sticky="w", pady=5)
        self.beta_var = tk.DoubleVar(value=1.0)
        ttk.Entry(form_frame, textvariable=self.beta_var).grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        ttk.Label(form_frame, text="(Higher = stricter shortest path)").grid(row=3, column=2, sticky="w", padx=5)

        form_frame.columnconfigure(1, weight=1)

        # Right column: Traffic Control
        right_col = ttk.LabelFrame(main_frame, text="Traffic Control (One-Way Corridors)", padding=16)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Treeview for edges
        columns = ("edge_id", "source", "target", "oneway")
        self.edge_tree = ttk.Treeview(right_col, columns=columns, show="headings", selectmode="browse")
        self.edge_tree.heading("edge_id", text="ID")
        self.edge_tree.heading("source", text="From")
        self.edge_tree.heading("target", text="To")
        self.edge_tree.heading("oneway", text="One-Way?")
        
        self.edge_tree.column("edge_id", width=50)
        self.edge_tree.column("source", width=80)
        self.edge_tree.column("target", width=80)
        self.edge_tree.column("oneway", width=60)
        
        self.edge_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Scrollbar for tree
        scrollbar = ttk.Scrollbar(right_col, orient=tk.VERTICAL, command=self.edge_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y) # This won't work well with pack side=top above. 
        # Fix layout:
        self.edge_tree.pack_forget()
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.edge_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.edge_tree.configure(yscrollcommand=scrollbar.set)
        
        # Toggle Button
        ttk.Button(right_col, text="Toggle One-Way Status", command=self._toggle_oneway).pack(side=tk.BOTTOM, pady=10)

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back", command=lambda: self.controller.show_frame("LayoutView"))
        back_btn.pack(side=tk.LEFT)
        
        next_btn = ttk.Button(nav_frame, text="Next: Run Simulation >", command=self._go_next)
        next_btn.pack(side=tk.RIGHT)

    def _populate_edge_list(self) -> None:
        """Fill the treeview with edges from the current floorplan."""
        for item in self.edge_tree.get_children():
            self.edge_tree.delete(item)
            
        floorplan = self.controller.state.get("floorplan")
        if not floorplan:
            return
            
        self.edge_oneway_states.clear()
        
        for edge in floorplan.edges:
            meta = edge.metadata or {}
            is_oneway = meta.get("oneway", False)
            self.edge_oneway_states[edge.edge_id] = is_oneway
            
            status_text = "Yes" if is_oneway else "No"
            self.edge_tree.insert("", tk.END, iid=edge.edge_id, values=(edge.edge_id, edge.source, edge.target, status_text))

    def _toggle_oneway(self) -> None:
        selected = self.edge_tree.selection()
        if not selected:
            return
            
        edge_id = selected[0]
        current_state = self.edge_oneway_states.get(edge_id, False)
        new_state = not current_state
        self.edge_oneway_states[edge_id] = new_state
        
        # Update UI
        status_text = "Yes" if new_state else "No"
        current_values = self.edge_tree.item(edge_id, "values")
        self.edge_tree.item(edge_id, values=(current_values[0], current_values[1], current_values[2], status_text))

    def _browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Scenario File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialdir=Path.cwd() / "data" / "samples"
        )
        if filename:
            self.file_path_var.set(filename)
            try:
                data = load_scenario(Path(filename))
                self.scenario_data = data
                
                # Auto-fill fields
                if "transition_window_s" in data:
                    self.duration_var.set(int(data["transition_window_s"]))
                if "random_seed" in data:
                    self.seed_var.set(int(data["random_seed"]))
                    
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load scenario: {e}")
                self.scenario_data = None
                self.file_path_var.set("")

    def _go_next(self) -> None:
        """Validate and save config, then navigate."""
        try:
            duration = self.duration_var.get()
            seed = self.seed_var.get()
            scale = self.scale_var.get()
            beta = self.beta_var.get()
            
            if duration <= 0:
                raise ValueError("Duration must be positive.")
            if scale <= 0:
                raise ValueError("Scale must be positive.")
            if beta < 0:
                raise ValueError("Beta must be non-negative.")
                
            self.controller.state["scenario_config"] = {
                "duration": duration,
                "seed": seed,
                "scale": scale,
                "beta": beta,
                "data": self.scenario_data # Pass the full scenario data if loaded
            }

            # Apply One-Way settings to the FloorPlan
            floorplan = self.controller.state.get("floorplan")
            if floorplan and self.edge_oneway_states:
                new_edges = []
                for edge in floorplan.edges:
                    is_oneway = self.edge_oneway_states.get(edge.edge_id, False)
                    
                    # Create a copy of metadata with updated oneway flag
                    new_meta = (edge.metadata or {}).copy()
                    new_meta["oneway"] = is_oneway
                    
                    # Create new EdgeSpec (since it's frozen)
                    new_edge = EdgeSpec(
                        edge_id=edge.edge_id,
                        source=edge.source,
                        target=edge.target,
                        length_m=edge.length_m,
                        width_m=edge.width_m,
                        capacity_pps=edge.capacity_pps,
                        is_stairs=edge.is_stairs,
                        metadata=new_meta
                    )
                    new_edges.append(new_edge)
                
                # Update the floorplan with modified edges
                floorplan.edges = new_edges
            
            self.controller.show_frame("RunView")
            
        except ValueError as e:
            messagebox.showerror("Invalid Configuration", str(e))
        except tk.TclError:
             messagebox.showerror("Invalid Configuration", "Please enter valid numbers.")
