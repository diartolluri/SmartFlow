"""View for selecting and loading floor plan layouts."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from smartflow.core.floorplan import load_floorplan

if TYPE_CHECKING:
    from ..app import SmartFlowApp


class LayoutView(ttk.Frame):
    """Frame for selecting and validating floor plan files."""

    def __init__(self, parent: ttk.Widget, controller: SmartFlowApp) -> None:
        super().__init__(parent, padding=16)
        self.controller = controller
        
        self._init_ui()

    def update_view(self) -> None:
        """Refresh UI if controller state has changed."""
        current_path = self.controller.state.get("floorplan_path")
        if current_path:
            # If path is different from what's displayed, or if we just want to ensure sync
            path_str = str(current_path)
            if self.path_var.get() != path_str:
                self.path_var.set(path_str)
                self._load_layout(path_str)

    def _init_ui(self) -> None:
        """Initialise UI components."""
        # Header
        header = ttk.Label(self, text="Step 1: Load Floor Plan & Traffic Rules", font=("Segoe UI", 16, "bold"))
        header.pack(pady=(0, 20))

        # Main Content - Split into Left (Load) and Right (Rules)
        content = ttk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True)
        
        left_pane = ttk.Frame(content)
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        right_pane = ttk.Frame(content)
        right_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Left Pane: File Loading ---
        file_frame = ttk.LabelFrame(left_pane, text="Floor Plan File", padding=16)
        file_frame.pack(fill=tk.X, pady=10)

        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(file_frame, textvariable=self.path_var, width=40, state="readonly")
        path_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)

        browse_btn = ttk.Button(file_frame, text="Browse...", command=self._browse_file)
        browse_btn.pack(side=tk.LEFT)
        
        # Edit Button
        self.edit_btn = ttk.Button(file_frame, text="Edit...", command=self._edit_current, state="disabled")
        self.edit_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Create New Button
        create_btn = ttk.Button(file_frame, text="Create New...", command=self._create_new)
        create_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Info Frame
        self.info_frame = ttk.LabelFrame(left_pane, text="Layout Summary", padding=16)
        self.info_frame.pack(fill=tk.BOTH, expand=True, pady=20)
        
        self.info_label = ttk.Label(self.info_frame, text="No layout loaded.")
        self.info_label.pack(anchor="nw")

        # --- Right Pane: Edge Management ---
        rules_frame = ttk.LabelFrame(right_pane, text="One-Way / Edge Toggles", padding=16)
        rules_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Treeview for edges
        columns = ("id", "source", "target", "status")
        self.edge_tree = ttk.Treeview(rules_frame, columns=columns, show="headings", selectmode="browse")
        self.edge_tree.heading("id", text="Edge ID")
        self.edge_tree.heading("source", text="From")
        self.edge_tree.heading("target", text="To")
        self.edge_tree.heading("status", text="Status")
        
        self.edge_tree.column("id", width=80)
        self.edge_tree.column("source", width=80)
        self.edge_tree.column("target", width=80)
        self.edge_tree.column("status", width=60)
        
        scrollbar = ttk.Scrollbar(rules_frame, orient=tk.VERTICAL, command=self.edge_tree.yview)
        self.edge_tree.configure(yscroll=scrollbar.set)
        
        self.edge_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Toggle Button
        btn_frame = ttk.Frame(right_pane)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.toggle_btn = ttk.Button(btn_frame, text="Toggle Selected Edge", command=self._toggle_edge, state="disabled")
        self.toggle_btn.pack(side=tk.RIGHT)

        # Navigation
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, pady=20, side=tk.BOTTOM)
        
        next_btn = ttk.Button(nav_frame, text="Next: Configuration >", command=self._go_next)
        next_btn.pack(side=tk.RIGHT)

    def _browse_file(self) -> None:
        """Open file dialog to select JSON layout."""
        # Try to start in the samples directory
        initial_dir = Path.cwd() / "data" / "samples"
        if not initial_dir.exists():
            initial_dir = Path.cwd()

        file_path = filedialog.askopenfilename(
            title="Select Floor Plan",
            initialdir=str(initial_dir),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            self.path_var.set(file_path)
            self._load_layout(file_path)

    def _load_layout(self, path_str: str) -> None:
        """Attempt to load and validate the layout."""
        try:
            path = Path(path_str)
            plan = load_floorplan(path)
            
            # Update controller state
            self.controller.state["floorplan"] = plan
            self.controller.state["floorplan_path"] = path
            self.controller.state["disabled_edges"] = set() # Reset disabled edges
            
            # Update UI
            summary = (
                f"Loaded: {path.name}\n"
                f"Nodes: {len(plan.nodes)}\n"
                f"Edges: {len(plan.edges)}\n"
                f"Total Length: {sum(e.length_m for e in plan.edges):.1f}m"
            )
            self.info_label.config(text=summary, foreground="black")
            
            # Populate Treeview
            self.edge_tree.delete(*self.edge_tree.get_children())
            for edge in plan.edges:
                self.edge_tree.insert(
                    "", 
                    tk.END, 
                    iid=edge.edge_id,
                    values=(edge.edge_id, edge.source, edge.target, "Active")
                )
            
            self.toggle_btn.config(state="normal")
            self.edit_btn.config(state="normal")
            
        except Exception as e:
            self.controller.state["floorplan"] = None
            self.info_label.config(text=f"Error loading layout:\n{e}", foreground="red")
            self.edit_btn.config(state="disabled")

    def _create_new(self) -> None:
        """Open editor with blank canvas."""
        # Clear current path so Editor knows it's a new file
        self.controller.state["floorplan_path"] = None
        
        editor = self.controller.frames["EditorView"]
        if hasattr(editor, "clear_and_reset"):
            editor.clear_and_reset()
        self.controller.show_frame("EditorView")

    def _edit_current(self) -> None:
        """Open editor with current floorplan."""
        plan = self.controller.state.get("floorplan")
        if not plan:
            return
            
        editor = self.controller.frames["EditorView"]
        if hasattr(editor, "load_from_floorplan"):
            editor.load_from_floorplan(plan)
        self.controller.show_frame("EditorView")

    def _toggle_edge(self) -> None:
        """Toggle the active status of the selected edge."""
        selected = self.edge_tree.selection()
        if not selected:
            return
            
        edge_id = selected[0]
        disabled_set = self.controller.state.get("disabled_edges", set())
        
        if edge_id in disabled_set:
            disabled_set.remove(edge_id)
            status = "Active"
            tag = ""
        else:
            disabled_set.add(edge_id)
            status = "DISABLED"
            tag = "disabled"
            
        self.controller.state["disabled_edges"] = disabled_set
        
        # Update Treeview
        current_values = self.edge_tree.item(edge_id, "values")
        self.edge_tree.item(edge_id, values=(current_values[0], current_values[1], current_values[2], status), tags=(tag,))
        
        # Add tag config for visual feedback
        self.edge_tree.tag_configure("disabled", foreground="red")

    def _go_next(self) -> None:
        """Navigate to the next view."""
        if not self.controller.state.get("floorplan"):
            messagebox.showwarning("Missing Layout", "Please load a valid floor plan first.")
            return
            
        self.controller.show_frame("ConfigView")
