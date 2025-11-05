"""Placeholder view for displaying simulation results."""

from __future__ import annotations

from tkinter import ttk


class ResultsView(ttk.Frame):
    """Frame for charts, heatmaps, and exports."""

    def __init__(self, master: ttk.Widget | None = None) -> None:
        super().__init__(master, padding=8)
        ttk.Label(self, text="Results view placeholder").pack()
