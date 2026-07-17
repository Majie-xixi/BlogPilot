from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from blogpost.ui.theme import COLORS, FONT


def _master_background(master) -> str:
    try:
        return str(master.cget("background"))
    except tk.TclError:
        pass
    try:
        style_name = str(master.cget("style")) or f"{master.winfo_class()}"
        return str(ttk.Style(master).lookup(style_name, "background") or COLORS["page"])
    except (AttributeError, tk.TclError):
        return COLORS["page"]


def _draw_rounded_rectangle(
    canvas: tk.Canvas,
    *,
    tag: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    fill: str,
    outline: str,
    width: int = 1,
) -> None:
    radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    diameter = radius * 2
    canvas.create_rectangle(
        x1 + radius,
        y1,
        x2 - radius,
        y2,
        fill=fill,
        outline="",
        tags=tag,
    )
    canvas.create_rectangle(
        x1,
        y1 + radius,
        x2,
        y2 - radius,
        fill=fill,
        outline="",
        tags=tag,
    )
    for left, top, start in (
        (x1, y1, 90),
        (x2 - diameter, y1, 0),
        (x2 - diameter, y2 - diameter, 270),
        (x1, y2 - diameter, 180),
    ):
        canvas.create_arc(
            left,
            top,
            left + diameter,
            top + diameter,
            start=start,
            extent=90,
            style="pieslice",
            fill=fill,
            outline=fill,
            tags=tag,
        )
        canvas.create_arc(
            left,
            top,
            left + diameter,
            top + diameter,
            start=start,
            extent=90,
            style="arc",
            outline=outline,
            width=width,
            tags=tag,
        )
    canvas.create_line(x1 + radius, y1, x2 - radius, y1, fill=outline, width=width, tags=tag)
    canvas.create_line(x2, y1 + radius, x2, y2 - radius, fill=outline, width=width, tags=tag)
    canvas.create_line(x2 - radius, y2, x1 + radius, y2, fill=outline, width=width, tags=tag)
    canvas.create_line(x1, y2 - radius, x1, y1 + radius, fill=outline, width=width, tags=tag)


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
        _draw_rounded_rectangle(
            self,
            tag="panel-shape",
            x1=1,
            y1=1,
            x2=width - 1,
            y2=height - 1,
            radius=self.radius,
            fill=self.fill,
            outline=self.border,
        )
        self.tag_lower("panel-shape")
        left, top, right, bottom = self.insets
        self.coords(self._window, left, top)
        self.itemconfigure(
            self._window,
            width=max(1, width - left - right),
            height=max(1, height - top - bottom),
        )


class RoundedButton(tk.Canvas):
    """Modern rounded button with the subset of Button API used by the app."""

    def __init__(
        self,
        master,
        *,
        text: str = "",
        textvariable: tk.StringVar | None = None,
        command=None,
        variant: str = "secondary",
        min_width: int = 0,
        height: int = 36,
        radius: int = 8,
        anchor: str = "center",
        padding_x: int = 14,
        font: tuple | None = None,
        outer: str | None = None,
        selected: bool = False,
        icon: str | None = None,
        chevron: bool = False,
        **kwargs,
    ):
        self._text = text
        self._textvariable = textvariable
        self._command = command
        self._variant = variant
        self._state = "normal"
        self._selected = selected
        self._hovered = False
        self._pressed = False
        self._anchor = anchor
        self._padding_x = padding_x
        self._min_width = min_width
        self._height = height
        self._radius = radius
        self._icon = icon
        self._chevron = chevron
        self._font_spec = font or (FONT, 9, "bold" if variant == "primary" else "normal")
        background = outer or _master_background(master)
        tk.Canvas.__init__(
            self,
            master,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            height=height,
            takefocus=True,
            cursor="hand2",
            **kwargs,
        )
        if textvariable is not None:
            textvariable.trace_add("write", self._variable_changed)
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Key-Return>", self._invoke_from_key)
        self.bind("<Key-space>", self._invoke_from_key)
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)
        self._update_requested_width()
        self.after_idle(self._draw)

    def _display_text(self) -> str:
        return self._textvariable.get() if self._textvariable is not None else self._text

    def _variable_changed(self, *_args) -> None:
        if self.winfo_exists():
            self._update_requested_width()
            self._draw()

    def _update_requested_width(self) -> None:
        measured = tkfont.Font(font=self._font_spec).measure(self._display_text())
        icon_space = 23 if self._icon else 0
        chevron_space = 18 if self._chevron else 0
        self.configure(
            width=max(
                self._min_width,
                measured + self._padding_x * 2 + icon_space + chevron_space,
            )
        )

    def _palette(self) -> tuple[str, str, str]:
        if self._state == "disabled":
            return COLORS["surface_alt"], COLORS["border"], COLORS["subtle"]
        if self._variant == "primary":
            return (
                COLORS["primary_hover"] if self._hovered or self._pressed else COLORS["primary"],
                COLORS["primary_hover"] if self._hovered else COLORS["primary"],
                "#FFFFFF",
            )
        if self._variant == "link":
            outer = str(self.cget("background"))
            return (
                COLORS["primary_soft"] if self._hovered else outer,
                COLORS["primary_soft"] if self._hovered else outer,
                COLORS["primary_hover"] if self._hovered else COLORS["primary"],
            )
        if self._variant == "identity":
            outer = str(self.cget("background"))
            fill = COLORS["surface"] if self._hovered or self._pressed else outer
            return fill, fill, COLORS["text"]
        if self._variant == "toggle" and self._selected:
            return COLORS["primary_soft"], COLORS["primary"], COLORS["primary"]
        return (
            COLORS["surface_alt"] if self._hovered or self._pressed else COLORS["surface"],
            COLORS["primary"] if self.focus_get() is self else COLORS["border"],
            COLORS["text"],
        )

    def _draw(self, _event=None) -> None:
        if not self.winfo_exists():
            return
        self.delete("button-shape")
        self.delete("button-label")
        self.delete("button-icon")
        self.delete("button-chevron")
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        fill, outline, foreground = self._palette()
        _draw_rounded_rectangle(
            self,
            tag="button-shape",
            x1=1,
            y1=1,
            x2=width - 1,
            y2=height - 1,
            radius=self._radius,
            fill=fill,
            outline=outline,
        )
        if self._anchor == "w":
            x = self._padding_x + (23 if self._icon else 0)
            anchor = "w"
        else:
            x = width // 2
            anchor = "center"
        self.create_text(
            x,
            height // 2,
            text=self._display_text(),
            fill=foreground,
            font=self._font_spec,
            anchor=anchor,
            tags="button-label",
        )
        if self._icon == "account":
            icon_x = self._padding_x + 7
            icon_color = COLORS["subtle"] if self._state == "disabled" else COLORS["muted"]
            self.create_oval(
                icon_x - 3,
                height // 2 - 8,
                icon_x + 3,
                height // 2 - 2,
                outline=icon_color,
                width=2,
                tags="button-icon",
            )
            self.create_line(
                icon_x - 7,
                height // 2 + 7,
                icon_x - 5,
                height // 2 + 2,
                icon_x,
                height // 2,
                icon_x + 5,
                height // 2 + 2,
                icon_x + 7,
                height // 2 + 7,
                smooth=True,
                width=2,
                fill=icon_color,
                tags="button-icon",
            )
        if self._chevron:
            chevron_x = width - self._padding_x - 4
            chevron_y = height // 2
            chevron_color = COLORS["subtle"] if self._state == "disabled" else COLORS["muted"]
            self.create_line(
                chevron_x - 4,
                chevron_y - 2,
                chevron_x,
                chevron_y + 2,
                chevron_x + 4,
                chevron_y - 2,
                fill=chevron_color,
                width=1,
                smooth=True,
                tags="button-chevron",
            )

    def _enter(self, _event=None) -> None:
        if self._state != "disabled":
            self._hovered = True
            self._draw()

    def _leave(self, _event=None) -> None:
        self._hovered = False
        self._pressed = False
        self._draw()

    def _press(self, _event=None) -> None:
        if self._state != "disabled":
            self.focus_set()
            self._pressed = True
            self._draw()

    def _release(self, event) -> None:
        if self._state == "disabled":
            return
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._pressed = False
        self._draw()
        if inside and self._command is not None:
            self._command()

    def _invoke_from_key(self, _event=None) -> str:
        if self._state != "disabled" and self._command is not None:
            self._command()
        return "break"

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        redraw = False
        if "text" in options:
            self._text = str(options.pop("text"))
            redraw = True
        if "textvariable" in options:
            self._textvariable = options.pop("textvariable")
            redraw = True
        if "command" in options:
            self._command = options.pop("command")
        if "state" in options:
            self._state = str(options.pop("state"))
            self.configure(cursor="arrow" if self._state == "disabled" else "hand2")
            redraw = True
        if "selected" in options:
            self._selected = bool(options.pop("selected"))
            redraw = True
        result = tk.Canvas.configure(self, **options) if options else None
        if redraw and self.winfo_exists():
            self._update_requested_width()
            self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == "text":
            return self._display_text()
        if key == "state":
            return self._state
        return tk.Canvas.cget(self, key)


class RoundedProgressBar(tk.Canvas):
    """Thin, borderless progress track that matches the rounded UI system."""

    def __init__(
        self,
        master,
        *,
        maximum: float = 100,
        value: float = 0,
        height: int = 4,
        track: str = "#E8E5E0",
        fill: str = COLORS["primary"],
        outer: str | None = None,
        **kwargs,
    ):
        self._maximum = max(1.0, float(maximum))
        self._value = float(value)
        self._track = track
        self._fill = fill
        self._bar_height = height
        tk.Canvas.__init__(
            self,
            master,
            height=height,
            background=outer or _master_background(master),
            borderwidth=0,
            highlightthickness=0,
            **kwargs,
        )
        self.bind("<Configure>", self._draw)
        self.after_idle(self._draw)

    def _draw(self, _event=None) -> None:
        if not self.winfo_exists():
            return
        self.delete("progress")
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        radius = max(1, height // 2)
        _draw_rounded_rectangle(
            self,
            tag="progress",
            x1=0,
            y1=0,
            x2=width - 1,
            y2=height - 1,
            radius=radius,
            fill=self._track,
            outline=self._track,
        )
        fraction = max(0.0, min(1.0, self._value / self._maximum))
        if fraction <= 0:
            return
        fill_width = max(height, round((width - 1) * fraction))
        _draw_rounded_rectangle(
            self,
            tag="progress",
            x1=0,
            y1=0,
            x2=min(width - 1, fill_width),
            y2=height - 1,
            radius=radius,
            fill=self._fill,
            outline=self._fill,
        )

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "maximum" in options:
            self._maximum = max(1.0, float(options.pop("maximum")))
        if "value" in options:
            self._value = float(options.pop("value"))
        options.pop("mode", None)
        result = tk.Canvas.configure(self, **options) if options else None
        if self.winfo_exists():
            self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == "maximum":
            return self._maximum
        if key == "value":
            return self._value
        return tk.Canvas.cget(self, key)

    def start(self, _interval=None) -> None:
        return None

    def stop(self) -> None:
        return None


class ModernCheckButton(RoundedButton):
    """Flat check control that avoids the native Windows checkbox appearance."""

    def __init__(self, master, *, text: str, variable: tk.BooleanVar, compact: bool = False, **kwargs):
        self.variable = variable
        self.label = text
        self.compact = compact
        super().__init__(
            master,
            command=self._toggle,
            variant="toggle",
            height=30 if compact else 36,
            radius=8,
            font=(FONT, 9),
            anchor="w",
            padding_x=8 if compact else 11,
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
            selected=selected,
        )
