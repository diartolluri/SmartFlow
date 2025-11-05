"""Tkinter application skeleton."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SmartFlowApp(tk.Tk):
    """Main window managing SmartFlow views."""

    def __init__(self) -> None:
        super().__init__()
        self.title("SmartFlow")
        self.geometry("1024x768")
        self._build_layout()

    def _build_layout(self) -> None:
        """Instantiate placeholder frames."""

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        label = ttk.Label(frame, text="SmartFlow UI coming soon")
        label.pack()


def launch() -> None:
    """Convenience entry point for running the Tkinter app."""

    app = SmartFlowApp()
    app.mainloop()
