"""Placeholder view for running simulations."""

from __future__ import annotations

from tkinter import ttk


class RunView(ttk.Frame):
    """Frame providing controls to run or stop simulations."""

    def __init__(self, master: ttk.Widget | None = None) -> None:
        super().__init__(master, padding=8)
        ttk.Label(self, text="Run view placeholder").pack()
