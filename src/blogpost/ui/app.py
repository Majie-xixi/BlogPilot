from __future__ import annotations

import tkinter as tk

from blogpost.application import build_context
from blogpost.logging_setup import configure_logging
from blogpost.paths import log_path
from blogpost.ui.main_window import MainWindow
from blogpost.ui.theme import configure_theme


def main() -> int:
    configure_logging(log_path())
    root = tk.Tk()
    root.title("BlogPilot · 智博日更")
    root.geometry("1040x740")
    root.minsize(900, 660)
    configure_theme(root)
    MainWindow(root, build_context())
    root.mainloop()
    return 0
