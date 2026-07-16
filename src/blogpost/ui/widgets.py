from __future__ import annotations

import tkinter as tk

from blogpost.ui.theme import COLORS, FONT


class ModernCheckButton(tk.Button):
    """Flat check control that avoids the native Windows checkbox appearance."""

    def __init__(self, master, *, text: str, variable: tk.BooleanVar, compact: bool = False, **kwargs):
        self.variable = variable
        self.label = text
        self.compact = compact
        super().__init__(
            master,
            command=self._toggle,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            font=(FONT, 9),
            anchor="w",
            cursor="hand2",
            padx=8 if compact else 11,
            pady=4 if compact else 7,
            **kwargs,
        )
        self.variable.trace_add("write", self._variable_changed)
        self._render()

    def _toggle(self) -> None:
        self.variable.set(not self.variable.get())

    def _variable_changed(self, *_args) -> None:
        if self.winfo_exists():
            self._render()

    def _render(self) -> None:
        selected = self.variable.get()
        self.configure(
            text=f"{'✓' if selected else ' '}  {self.label}",
            background=COLORS["primary_soft"] if selected else COLORS["surface"],
            activebackground=COLORS["primary_soft"],
            foreground=COLORS["primary"] if selected else COLORS["text"],
            activeforeground=COLORS["primary"],
            highlightbackground=COLORS["primary"] if selected else COLORS["border"],
            highlightcolor=COLORS["primary"],
        )
