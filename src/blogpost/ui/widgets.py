from __future__ import annotations

import tkinter as tk

from blogpost.ui.theme import COLORS, FONT


class RoundedPanel(tk.Canvas):
    """Canvas-backed container with real rounded corners for Tkinter layouts."""

    def __init__(
        self,
        master,
        *,
        radius: int = 12,
        padding: tuple[int, int] | tuple[int, int, int, int] = (16, 14),
        fill: str = COLORS["surface"],
        border: str = COLORS["border"],
        outer: str = COLORS["page"],
        **kwargs,
    ):
        if len(padding) == 2:
            horizontal, vertical = padding
            self.insets = (horizontal, vertical, horizontal, vertical)
        else:
            self.insets = padding
        self.radius = radius
        self.fill = fill
        self.border = border
        super().__init__(
            master,
            background=outer,
            borderwidth=0,
            highlightthickness=0,
            **kwargs,
        )
        self.content = tk.Frame(self, background=fill, borderwidth=0, highlightthickness=0)
        self._window = self.create_window(0, 0, anchor="nw", window=self.content)
        self.bind("<Configure>", self._redraw)
        self.content.bind("<Configure>", self._content_resized)

    def _content_resized(self, _event=None) -> None:
        left, top, right, bottom = self.insets
        requested_width = self.content.winfo_reqwidth() + left + right
        requested_height = self.content.winfo_reqheight() + top + bottom
        if requested_width != self.winfo_reqwidth():
            self.configure(width=requested_width)
        if requested_height != self.winfo_reqheight():
            self.configure(height=requested_height)

    def _redraw(self, _event=None) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("panel-shape")
        radius = min(self.radius, width // 2, height // 2)
        diameter = radius * 2
        self.create_rectangle(
            radius,
            1,
            width - radius,
            height - 1,
            fill=self.fill,
            outline="",
            tags="panel-shape",
        )
        self.create_rectangle(
            1,
            radius,
            width - 1,
            height - radius,
            fill=self.fill,
            outline="",
            tags="panel-shape",
        )
        for x1, y1, start in (
            (1, 1, 90),
            (width - diameter - 1, 1, 0),
            (width - diameter - 1, height - diameter - 1, 270),
            (1, height - diameter - 1, 180),
        ):
            self.create_arc(
                x1,
                y1,
                x1 + diameter,
                y1 + diameter,
                start=start,
                extent=90,
                style="pieslice",
                fill=self.fill,
                outline=self.fill,
                tags="panel-shape",
            )
            self.create_arc(
                x1,
                y1,
                x1 + diameter,
                y1 + diameter,
                start=start,
                extent=90,
                style="arc",
                outline=self.border,
                width=1,
                tags="panel-shape",
            )
        self.create_line(radius, 1, width - radius, 1, fill=self.border, tags="panel-shape")
        self.create_line(
            width - 1,
            radius,
            width - 1,
            height - radius,
            fill=self.border,
            tags="panel-shape",
        )
        self.create_line(
            width - radius,
            height - 1,
            radius,
            height - 1,
            fill=self.border,
            tags="panel-shape",
        )
        self.create_line(1, height - radius, 1, radius, fill=self.border, tags="panel-shape")
        self.tag_lower("panel-shape")
        left, top, right, bottom = self.insets
        self.coords(self._window, left, top)
        self.itemconfigure(
            self._window,
            width=max(1, width - left - right),
            height=max(1, height - top - bottom),
        )


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
