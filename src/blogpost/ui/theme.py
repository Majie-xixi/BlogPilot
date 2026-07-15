from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "page": "#F6F8FB",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "border": "#D8E0EA",
    "text": "#17202B",
    "muted": "#64748B",
    "subtle": "#94A3B8",
    "primary": "#1F9F78",
    "primary_hover": "#188966",
    "primary_soft": "#ECFDF3",
    "success": "#15803D",
    "warning": "#A16207",
    "danger": "#B91C1C",
}

FONT = "Microsoft YaHei UI"


def configure_theme(root: tk.Tk) -> None:
    """Apply a compact modern theme using only bundled Tk widgets."""
    root.configure(background=COLORS["page"])
    root.option_add("*Font", (FONT, 10))
    root.option_add("*tearOff", False)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(FONT, 10), focuscolor="")
    style.configure("Page.TFrame", background=COLORS["page"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure(
        "Card.TFrame",
        background=COLORS["surface"],
        borderwidth=1,
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        relief="solid",
    )
    style.configure(
        "Hero.TFrame",
        background=COLORS["surface"],
        borderwidth=1,
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        relief="solid",
    )

    style.configure("TLabel", background=COLORS["page"], foreground=COLORS["text"])
    style.configure(
        "Title.TLabel",
        background=COLORS["page"],
        foreground=COLORS["text"],
        font=(FONT, 24, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=COLORS["page"],
        foreground=COLORS["muted"],
        font=(FONT, 10),
    )
    style.configure(
        "Section.TLabel",
        background=COLORS["page"],
        foreground=COLORS["text"],
        font=(FONT, 12, "bold"),
    )
    style.configure(
        "CardCaption.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=(FONT, 9),
    )
    style.configure(
        "CardValue.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=(FONT, 14, "bold"),
    )
    style.configure(
        "CardDetail.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=(FONT, 9),
    )
    style.configure(
        "HeroTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=(FONT, 16, "bold"),
    )
    style.configure(
        "HeroText.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=(FONT, 9),
    )
    style.configure(
        "DialogTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=(FONT, 18, "bold"),
    )
    style.configure(
        "DialogText.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=(FONT, 9),
    )
    style.configure(
        "Field.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=(FONT, 9, "bold"),
    )

    style.configure(
        "Primary.TButton",
        background=COLORS["primary"],
        foreground="#FFFFFF",
        borderwidth=0,
        padding=(18, 10),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", "#AFC5F5"), ("active", COLORS["primary_hover"])],
        foreground=[("disabled", "#EEF3FF")],
    )
    style.configure(
        "HeroButton.TButton",
        background=COLORS["primary"],
        foreground="#FFFFFF",
        borderwidth=0,
        padding=(20, 11),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "HeroButton.TButton",
        background=[("active", COLORS["primary_hover"]), ("disabled", "#A7D8C8")],
        foreground=[("disabled", "#F2FBF8")],
    )
    style.configure(
        "Secondary.TButton",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        borderwidth=1,
        padding=(14, 8),
    )
    style.map("Secondary.TButton", background=[("active", COLORS["surface_alt"])])
    style.configure(
        "Link.TButton",
        background=COLORS["page"],
        foreground=COLORS["primary"],
        borderwidth=0,
        padding=(8, 4),
        font=(FONT, 9, "bold"),
    )
    style.map(
        "Link.TButton",
        background=[("active", COLORS["page"])],
        foreground=[("active", COLORS["primary_hover"])],
    )

    style.configure(
        "Modern.TEntry",
        fieldbackground=COLORS["surface_alt"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        insertcolor=COLORS["text"],
        borderwidth=1,
        padding=(10, 9),
    )
    style.map("Modern.TEntry", bordercolor=[("focus", COLORS["primary"])])
    style.configure(
        "Modern.TCheckbutton",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        padding=(0, 4),
    )
    style.map("Modern.TCheckbutton", background=[("active", COLORS["surface"])])

    style.configure(
        "Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        borderwidth=0,
        relief="flat",
        rowheight=37,
        font=(FONT, 9),
    )
    style.map("Treeview", background=[("selected", COLORS["primary_soft"])], foreground=[("selected", COLORS["text"])])
    style.configure(
        "Treeview.Heading",
        background=COLORS["surface_alt"],
        foreground=COLORS["muted"],
        borderwidth=0,
        relief="flat",
        padding=(10, 10),
        font=(FONT, 9, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", COLORS["surface_alt"])])
    style.configure(
        "Vertical.TScrollbar",
        background="#CBD5E1",
        troughcolor=COLORS["surface_alt"],
        borderwidth=0,
        arrowsize=0,
    )
    style.configure(
        "App.Horizontal.TProgressbar",
        troughcolor="#E2E8F0",
        background=COLORS["primary"],
        borderwidth=0,
        lightcolor=COLORS["primary"],
        darkcolor=COLORS["primary"],
        thickness=5,
    )
    style.configure("TNotebook", background=COLORS["page"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=COLORS["page"],
        foreground=COLORS["muted"],
        borderwidth=0,
        padding=(18, 9),
        font=(FONT, 9, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["surface"])],
        foreground=[("selected", COLORS["primary"])],
    )
