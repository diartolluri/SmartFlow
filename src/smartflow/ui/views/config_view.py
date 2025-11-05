"""Placeholder view for scenario configuration."""

from __future__ import annotations

from tkinter import ttk


class ConfigView(ttk.Frame):
    """Frame for editing schedule and population settings."""

    def __init__(self, master: ttk.Widget | None = None) -> None:
        super().__init__(master, padding=8)
        ttk.Label(self, text="Configuration view placeholder").pack()
