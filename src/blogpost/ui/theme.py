from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "page": "#FAFAF8",
    "surface": "#FFFFFF",
    "surface_alt": "#F7F6F3",
    "control": "#F1EFEA",
    "control_hover": "#E9E6DF",
    "border": "#E3E1DC",
    "text": "#20201E",
    "muted": "#74736F",
    "subtle": "#A09E98",
    "primary": "#D45F3A",
    "primary_hover": "#BC4D2B",
    "primary_soft": "#FFF0EA",
    "danger_soft": "#FEF2F2",
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
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "StatusCard.TFrame",
        background=COLORS["surface"],
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "OutlinedCard.TFrame",
        background=COLORS["surface"],
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "Hero.TFrame",
        background=COLORS["surface"],
        borderwidth=0,
        relief="flat",
    )

    style.configure("TLabel", background=COLORS["page"], foreground=COLORS["text"])
    style.configure(
        "Title.TLabel",
        background=COLORS["page"],
        foreground=COLORS["text"],
        font=(FONT, 21, "bold"),
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
        font=(FONT, 10, "bold"),
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
        font=(FONT, 13, "bold"),
    )
    style.configure(
        "CardSuccessValue.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["success"],
        font=(FONT, 13, "bold"),
    )
    style.configure(
        "CardWarningValue.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["warning"],
        font=(FONT, 13, "bold"),
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
        font=(FONT, 13, "bold"),
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
        padding=(18, 9),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", "#E5B6A6"), ("active", COLORS["primary_hover"])],
        foreground=[("disabled", "#FFF7F4")],
    )
    style.configure(
        "HeroButton.TButton",
        background=COLORS["primary"],
        foreground="#FFFFFF",
        borderwidth=0,
        padding=(20, 10),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "HeroButton.TButton",
        background=[("active", COLORS["primary_hover"]), ("disabled", "#E5B6A6")],
        foreground=[("disabled", "#FFF7F4")],
    )
    style.configure(
        "HeroSecondary.TButton",
        background=COLORS["control"],
        foreground=COLORS["text"],
        borderwidth=0,
        padding=(17, 9),
        font=(FONT, 9),
    )
    style.map(
        "HeroSecondary.TButton",
        background=[("active", COLORS["control_hover"]), ("disabled", COLORS["surface_alt"])],
        foreground=[("disabled", COLORS["subtle"])],
    )
    style.configure(
        "Secondary.TButton",
        background=COLORS["control"],
        foreground=COLORS["text"],
        borderwidth=0,
        padding=(13, 7),
        font=(FONT, 9),
    )
    style.map("Secondary.TButton", background=[("active", COLORS["control_hover"])])
    style.configure(
        "Link.TButton",
        background=COLORS["page"],
        foreground=COLORS["primary"],
        borderwidth=0,
        padding=(4, 2),
        font=(FONT, 9),
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
        troughcolor="#E8EDF3",
        background=COLORS["primary"],
        borderwidth=0,
        bordercolor="#E8EDF3",
        relief="flat",
        troughrelief="flat",
        lightcolor=COLORS["primary"],
        darkcolor=COLORS["primary"],
        thickness=4,
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
