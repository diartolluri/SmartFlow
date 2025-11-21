"""View for configuring simulation parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from typing import TYPE_CHECKING
from pathlib import Path

from ...io.importers import load_scenario

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class ConfigView(ttk.Frame):
    """Frame for editing schedule and population settings."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        self.scenario_data = None
        
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Header
        header = ttk.Label(self, text="Step 2: Configuration", font=("Segoe UI", 16, "bold"))
        header.pack(pady=(0, 20))

        # Scenario File Selection
        file_frame = ttk.LabelFrame(self, text="Scenario File (Optional)", padding=16)
        file_frame.pack(fill=tk.X, pady=10)
        
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(file_frame, text="Browse...", command=self._browse_file).pack(side=tk.RIGHT)

        # Form Frame
        form_frame = ttk.LabelFrame(self, text="Simulation Parameters", padding=16)
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

        form_frame.columnconfigure(1, weight=1)

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        back_btn = ttk.Button(nav_frame, text="< Back", command=lambda: self.controller.show_frame("LayoutView"))
        back_btn.pack(side=tk.LEFT)
        
        next_btn = ttk.Button(nav_frame, text="Next: Run Simulation >", command=self._go_next)
        next_btn.pack(side=tk.RIGHT)

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
            
            self.controller.show_frame("RunView")
            
        except ValueError as e:
            messagebox.showerror("Invalid Configuration", str(e))
        except tk.TclError:
             messagebox.showerror("Invalid Configuration", "Please enter valid numbers.")
