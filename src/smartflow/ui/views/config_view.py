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
        self._autoloaded_for_layout: str | None = None
        self._manual_scenario_selected = False
        self.edge_oneway_states = {} # Map edge_id -> bool
        
        self._init_ui()

    def update_view(self) -> None:
        """Refresh UI with data from controller state."""
        self._populate_edge_list()
        
        # Auto-load scenario if one exists for this floorplan.
        # Key rule: if the layout changed, prefer the matching [layout]_scenario.json
        # so multi-period runs (e.g. lesson changeover) work without manual browsing.
        floorplan_path = self.controller.state.get("floorplan_path")
        if floorplan_path:
            path_obj = Path(floorplan_path)
            # Look for [name]_scenario.json
            scen_path = path_obj.with_name(path_obj.stem + "_scenario.json")
            
            current_file = self.file_path_var.get()

            should_autoload = False
            if scen_path.exists():
                # If layout changed since we were last here, autoload the matching scenario.
                if self._autoloaded_for_layout != str(path_obj):
                    should_autoload = True
                # If no scenario selected yet (or selection is missing), autoload.
                if not current_file:
                    should_autoload = True
                else:
                    try:
                        if not Path(current_file).exists():
                            should_autoload = True
                    except Exception:
                        should_autoload = True

                # Respect manual selection unless it's the same file.
                if self._manual_scenario_selected and current_file:
                    try:
                        if Path(current_file).name != scen_path.name:
                            should_autoload = False
                    except Exception:
                        pass

            if should_autoload:
                print(f"Auto-loading scenario: {scen_path}")
                self.file_path_var.set(str(scen_path))
                try:
                    data = load_scenario(scen_path)
                    self.scenario_data = data
                    self._autoloaded_for_layout = str(path_obj)

                    if "transition_window_s" in data:
                        self.duration_var.set(int(data["transition_window_s"]))
                    if "random_seed" in data:
                        self.seed_var.set(int(data["random_seed"]))
                except Exception as e:
                    print(f"Failed to auto-load scenario: {e}")

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Step 2: Configuration", font=("Segoe UI Semibold", 16))
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
        dur_label = ttk.Label(form_frame, text="Duration (seconds):")
        dur_label.grid(row=0, column=0, sticky="w", pady=5)
        self.duration_var = tk.IntVar(value=300)
        ttk.Entry(form_frame, textvariable=self.duration_var).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        # Random Seed
        seed_label = ttk.Label(form_frame, text="Random Seed:")
        seed_label.grid(row=1, column=0, sticky="w", pady=5)
        self.seed_var = tk.IntVar(value=42)
        ttk.Entry(form_frame, textvariable=self.seed_var).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Population Scale (Optional)
        scale_label = ttk.Label(form_frame, text="Population Scale:")
        scale_label.grid(row=2, column=0, sticky="w", pady=5)
        self.scale_var = tk.DoubleVar(value=1.0)
        ttk.Entry(form_frame, textvariable=self.scale_var).grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        form_frame.columnconfigure(1, weight=1)
        
        # Add tooltips to explain parameters
        try:
            from ..app import create_tooltip
            create_tooltip(dur_label, "How long the simulation runs (lesson changeover time)")
            create_tooltip(seed_label, "Random seed for reproducible results. Same seed = same simulation")
            create_tooltip(scale_label, "Multiply agent count (0.5 = half, 2.0 = double population)")
        except Exception:
            pass

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back", command=lambda: self.controller.show_frame("LayoutView"))
        back_btn.pack(side=tk.LEFT)
        
        next_btn = ttk.Button(nav_frame, text="Next: Run Simulation >", command=self._go_next)
        next_btn.pack(side=tk.RIGHT)

    def _populate_edge_list(self) -> None:
        """Fill the treeview with edges from the current floorplan."""
        # Feature removed but method kept for safe update_view calls
        pass

    def _toggle_oneway(self) -> None:
        pass

    def _browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Scenario File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialdir=Path.cwd() / "data" / "samples"
        )
        if filename:
            self._manual_scenario_selected = True
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
            
            if duration <= 0:
                raise ValueError("Duration must be positive.")
            if scale <= 0:
                raise ValueError("Scale must be positive.")
                
            self.controller.state["scenario_config"] = {
                "duration": duration,
                "seed": seed,
                "scale": scale,
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
