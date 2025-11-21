"""Tkinter application main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict

from .views.config_view import ConfigView
from .views.layout_view import LayoutView
from .views.results_view import ResultsView
from .views.run_view import RunView
from .views.comparison_view import ComparisonView


class SmartFlowApp(tk.Tk):
    """Main window managing SmartFlow views."""

    def __init__(self) -> None:
        super().__init__()
        self.title("SmartFlow - School Corridor Simulator")
        self.geometry("1200x800")
        
        # Shared state
        self.state: Dict[str, Any] = {
            "floorplan": None,
            "floorplan_path": None,
            "scenario_config": {},
            "simulation_results": None
        }
        
        self._build_layout()

    def _build_layout(self) -> None:
        """Instantiate frames and navigation."""
        
        # Container for all views
        self.container = ttk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)
        
        # Dictionary to hold view instances
        self.frames: Dict[str, ttk.Frame] = {}
        
        # Instantiate views
        for F in (LayoutView, ConfigView, RunView, ResultsView, ComparisonView):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")
            
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        # Start at LayoutView
        self.show_frame("LayoutView")

    def show_frame(self, page_name: str) -> None:
        """Raise a frame to the top."""
        frame = self.frames[page_name]
        frame.tkraise()
        # Trigger refresh if the view has an update method
        if hasattr(frame, "update_view"):
            frame.update_view()


def launch() -> None:
    """Convenience entry point for running the Tkinter app."""
    app = SmartFlowApp()
    app.mainloop()
