"""Placeholder view for layout loading."""

from __future__ import annotations

from tkinter import ttk


class LayoutView(ttk.Frame):
    """Frame for selecting and validating floor plan files."""

    def __init__(self, master: ttk.Widget | None = None) -> None:
        super().__init__(master, padding=8)
        ttk.Label(self, text="Layout view placeholder").pack()
