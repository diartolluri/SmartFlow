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
from .views.editor_view import EditorView


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
        
        self._configure_styles()
        self._build_layout()

    def _configure_styles(self) -> None:
        """Apply a dark theme to the application."""
        style = ttk.Style(self)
        style.theme_use("clam")  # 'clam' allows for easier color customization

        # Colors
        bg_color = "#2b2b2b"
        fg_color = "#ffffff"
        accent_color = "#007acc"
        secondary_bg = "#3c3c3c"
        
        self.configure(background=bg_color)

        # Configure generic styles
        # Phase 1: Cleaner Font (Segoe UI / San Francisco style)
        default_font = ("Segoe UI", 10)
        header_font = ("Segoe UI", 12, "bold")

        style.configure(".", 
            background=bg_color, 
            foreground=fg_color, 
            fieldbackground=secondary_bg,
            troughcolor=bg_color,
            selectbackground=accent_color,
            selectforeground=fg_color,
            font=default_font
        )
        
        # Frames
        style.configure("TFrame", background=bg_color)
        style.configure("TLabelframe", background=bg_color, foreground=fg_color)
        style.configure("TLabelframe.Label", background=bg_color, foreground=fg_color, font=default_font)
        
        # Labels
        style.configure("TLabel", background=bg_color, foreground=fg_color, font=default_font)
        style.configure("Header.TLabel", font=header_font, foreground=accent_color)
        
        # Buttons
        style.configure("TButton", 
            background=secondary_bg, 
            foreground=fg_color, 
            font=default_font, 
            borderwidth=1,
            focusthickness=3,
            focuscolor=accent_color
        )
        style.map("TButton",
            background=[("active", "#505050"), ("pressed", "#606060")],
            foreground=[("disabled", "#888888")]
        )
        
        # Entries
        style.configure("TEntry", 
            fieldbackground=secondary_bg,
            foreground=fg_color,
            insertcolor=fg_color
        )
        
        # Treeview
        style.configure("Treeview", 
            background=secondary_bg,
            foreground=fg_color,
            fieldbackground=secondary_bg,
            borderwidth=0
        )
        style.configure("Treeview.Heading", 
            background="#404040", 
            foreground=fg_color,
            relief="flat"
        )
        style.map("Treeview", 
            background=[("selected", accent_color)],
            foreground=[("selected", fg_color)]
        )

    def _build_layout(self) -> None:
        """Instantiate frames and navigation."""
        
        # Container for all views
        self.container = ttk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)
        
        # Dictionary to hold view instances
        self.frames: Dict[str, ttk.Frame] = {}
        
        # Instantiate views
        for F in (LayoutView, ConfigView, RunView, ResultsView, ComparisonView, EditorView):
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
