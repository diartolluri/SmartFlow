"""Tkinter application main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict

from .views.config_view import ConfigView
from .views.layout_view import LayoutView
from .views.results_view import ResultsView
from .views.run_view import RunView
from .views.comparison_view import ComparisonView
from .views.editor_view import EditorView


# Application metadata
APP_VERSION = "1.0.0"
APP_AUTHOR = "NEA Project"
APP_DESCRIPTION = "Agent-based simulation for analysing school corridor congestion."

# Modern UI Colors (exported for use in views)
COLORS = {
    "bg": "#1e1e1e",
    "bg_secondary": "#2d2d2d",
    "fg": "#e0e0e0",
    "fg_muted": "#888888",
    "accent": "#0078d4",
    "accent_hover": "#1a86d9",
    "border": "#404040",
    "hover": "#3a3a3a",
    "success": "#4caf50",
    "warning": "#ff9800",
    "error": "#f44336",
}

# Modern Fonts
FONTS = {
    "default": ("Segoe UI", 10),
    "small": ("Segoe UI", 9),
    "medium": ("Segoe UI", 11),
    "header": ("Segoe UI Semibold", 12),
    "title": ("Segoe UI Semibold", 14),
    "large_title": ("Segoe UI Semibold", 16),
}


class RoundedFrame(tk.Canvas):
    """A frame with rounded corners using Canvas."""
    
    def __init__(self, parent, bg_color="#2d2d2d", corner_radius=12, **kwargs):
        # Extract padding if provided
        self.padding = kwargs.pop("padding", 16)
        super().__init__(parent, highlightthickness=0, bg=COLORS["bg"], **kwargs)
        
        self.bg_color = bg_color
        self.corner_radius = corner_radius
        
        # Inner frame to hold content
        self.inner_frame = ttk.Frame(self)
        self.inner_window = self.create_window(
            self.padding, self.padding, 
            window=self.inner_frame, 
            anchor="nw"
        )
        
        self.bind("<Configure>", self._on_resize)
    
    def _on_resize(self, event):
        """Redraw rounded rectangle on resize."""
        self.delete("rounded_bg")
        width = event.width
        height = event.height
        r = self.corner_radius
        
        # Draw rounded rectangle
        self.create_rounded_rect(0, 0, width, height, r, fill=self.bg_color, tags="rounded_bg")
        self.tag_lower("rounded_bg")
        
        # Update inner frame size
        self.itemconfig(self.inner_window, width=width - 2*self.padding, height=height - 2*self.padding)
    
    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        """Draw a rounded rectangle."""
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)


class ToolTip:
    """Simple tooltip for widgets."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)
        
    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)
        
    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

def create_tooltip(widget, text):
    """Factory for tooltips."""
    return ToolTip(widget, text)


def create_tooltip(widget: tk.Widget, text: str) -> None:
    """Attach a hover tooltip to a widget."""
    tip_window = None

    def show_tip(event: tk.Event) -> None:
        nonlocal tip_window
        if tip_window or not text:
            return
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 5
        tip_window = tk.Toplevel(widget)
        tip_window.wm_overrideredirect(True)
        tip_window.wm_geometry(f"+{x}+{y}")
        
        # Modern tooltip style
        tip_frame = tk.Frame(tip_window, bg=COLORS["bg_secondary"], padx=1, pady=1)
        tip_frame.pack()
        label = tk.Label(
            tip_frame, text=text, justify=tk.LEFT,
            background=COLORS["bg_secondary"], 
            foreground=COLORS["fg"],
            font=FONTS["small"],
            padx=8, pady=4
        )
        label.pack()

    def hide_tip(event: tk.Event) -> None:
        nonlocal tip_window
        if tip_window:
            tip_window.destroy()
            tip_window = None

    widget.bind("<Enter>", show_tip, add="+")
    widget.bind("<Leave>", hide_tip, add="+")


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
        self._build_menu()
        self._build_layout()
        self._bind_global_shortcuts()

    def _configure_styles(self) -> None:
        """Apply a modern dark theme to the application."""
        style = ttk.Style(self)
        style.theme_use("clam")  # 'clam' allows for easier color customization

        # Modern Colors
        bg_color = "#1e1e1e"       # Darker background
        fg_color = "#e0e0e0"       # Softer white
        accent_color = "#0078d4"   # Modern blue
        secondary_bg = "#2d2d2d"   # Card background
        border_color = "#404040"   # Subtle borders
        hover_color = "#3a3a3a"    # Hover state
        
        self.configure(background=bg_color)

        # Modern Font Stack
        # Using Inter-like appearance with Segoe UI (Windows) fallback
        default_font = ("Segoe UI", 10)
        small_font = ("Segoe UI", 9)
        header_font = ("Segoe UI Semibold", 12)
        title_font = ("Segoe UI Semibold", 14)

        style.configure(".", 
            background=bg_color, 
            foreground=fg_color, 
            fieldbackground=secondary_bg,
            troughcolor=bg_color,
            selectbackground=accent_color,
            selectforeground="#ffffff",
            font=default_font,
            borderwidth=0,
            relief="flat"
        )
        
        # Frames - clean with subtle padding
        style.configure("TFrame", background=bg_color)
        
        # LabelFrames - modern card-like appearance
        style.configure("TLabelframe", 
            background=secondary_bg, 
            foreground=fg_color,
            borderwidth=1,
            relief="solid",
            bordercolor=border_color
        )
        style.configure("TLabelframe.Label", 
            background=secondary_bg, 
            foreground=fg_color, 
            font=("Segoe UI Semibold", 10),
            padding=(8, 4)
        )
        
        # Labels
        style.configure("TLabel", background=bg_color, foreground=fg_color, font=default_font)
        style.configure("Header.TLabel", font=header_font, foreground=accent_color)
        style.configure("Title.TLabel", font=title_font, foreground="#ffffff")
        style.configure("Muted.TLabel", font=small_font, foreground="#888888")
        
        # Modern Buttons - pill-like appearance
        style.configure("TButton", 
            background=secondary_bg, 
            foreground=fg_color, 
            font=default_font, 
            borderwidth=1,
            padding=(12, 6),
            focusthickness=0,
            focuscolor=accent_color
        )
        style.map("TButton",
            background=[("active", hover_color), ("pressed", "#505050")],
            foreground=[("disabled", "#666666")],
            bordercolor=[("focus", accent_color)]
        )
        
        # Accent Button style
        style.configure("Accent.TButton",
            background=accent_color,
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(12, 6)
        )
        style.map("Accent.TButton",
            background=[("active", "#1a86d9"), ("pressed", "#005a9e")]
        )
        
        # Entries - modern with subtle border
        style.configure("TEntry", 
            fieldbackground=secondary_bg,
            foreground=fg_color,
            insertcolor=fg_color,
            borderwidth=1,
            padding=6
        )
        style.map("TEntry",
            bordercolor=[("focus", accent_color)]
        )
        
        # Spinbox
        style.configure("TSpinbox",
            fieldbackground=secondary_bg,
            foreground=fg_color,
            arrowcolor=fg_color,
            borderwidth=1,
            padding=4
        )
        
        # Combobox
        style.configure("TCombobox",
            fieldbackground=secondary_bg,
            foreground=fg_color,
            arrowcolor=fg_color,
            borderwidth=1,
            padding=4
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", secondary_bg)],
            selectbackground=[("readonly", accent_color)]
        )
        
        # Checkbutton
        style.configure("TCheckbutton",
            background=bg_color,
            foreground=fg_color,
            font=default_font,
            indicatormargin=4
        )
        style.map("TCheckbutton",
            background=[("active", bg_color)],
            indicatorcolor=[("selected", accent_color), ("!selected", secondary_bg)]
        )
        
        # Radiobutton
        style.configure("TRadiobutton",
            background=bg_color,
            foreground=fg_color,
            font=default_font,
            indicatormargin=4
        )
        style.map("TRadiobutton",
            background=[("active", bg_color)],
            indicatorcolor=[("selected", accent_color), ("!selected", secondary_bg)]
        )
        
        # Notebook (Tabs) - modern flat tabs
        style.configure("TNotebook", 
            background=bg_color,
            borderwidth=0
        )
        style.configure("TNotebook.Tab",
            background=secondary_bg,
            foreground=fg_color,
            font=default_font,
            padding=(16, 8),
            borderwidth=0
        )
        style.map("TNotebook.Tab",
            background=[("selected", accent_color), ("active", hover_color)],
            foreground=[("selected", "#ffffff")],
            expand=[("selected", [0, 0, 0, 2])]
        )
        
        # Treeview - clean table style
        style.configure("Treeview", 
            background=secondary_bg,
            foreground=fg_color,
            fieldbackground=secondary_bg,
            borderwidth=0,
            font=default_font,
            rowheight=28
        )
        style.configure("Treeview.Heading", 
            background=hover_color, 
            foreground=fg_color,
            font=("Segoe UI Semibold", 10),
            relief="flat",
            padding=6
        )
        style.map("Treeview", 
            background=[("selected", accent_color)],
            foreground=[("selected", "#ffffff")]
        )
        
        # Progressbar - modern slim style
        style.configure("TProgressbar",
            background=accent_color,
            troughcolor=secondary_bg,
            borderwidth=0,
            thickness=6
        )
        
        # Scale/Slider
        style.configure("TScale",
            background=bg_color,
            troughcolor=secondary_bg,
            sliderrelief="flat"
        )
        style.configure("Horizontal.TScale",
            sliderlength=20
        )
        
        # Separator
        style.configure("TSeparator",
            background=border_color
        )
        
        # Scrollbar - thin modern style
        style.configure("TScrollbar",
            background=secondary_bg,
            troughcolor=bg_color,
            borderwidth=0,
            arrowsize=12
        )
        style.map("TScrollbar",
            background=[("active", hover_color)]
        )

    def _build_menu(self) -> None:
        """Create the application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About SmartFlow", command=self._show_about)

    def _show_about(self) -> None:
        """Display the About dialog."""
        messagebox.showinfo(
            "About SmartFlow",
            f"SmartFlow v{APP_VERSION}\n\n"
            f"{APP_DESCRIPTION}\n\n"
            f"Author: {APP_AUTHOR}"
        )

    def _bind_global_shortcuts(self) -> None:
        """Bind application-wide keyboard shortcuts."""
        # Space to pause/resume simulation (handled in RunView via this binding)
        self.bind("<space>", self._toggle_simulation)

    def _toggle_simulation(self, event: tk.Event = None) -> None:
        """Toggle pause/resume on the RunView simulation."""
        run_view = self.frames.get("RunView")
        if run_view and hasattr(run_view, "is_running"):
            if run_view.is_running:
                run_view._stop_simulation()
            elif run_view.model is not None:
                run_view._resume_simulation()

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
