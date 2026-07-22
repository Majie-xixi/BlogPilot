from __future__ import annotations

import tkinter as tk

from blogpost.application import build_context
from blogpost.logging_setup import configure_logging
from blogpost.paths import log_path
from blogpost.ui.first_run import ensure_data_directory
from blogpost.ui.main_window import MainWindow
from blogpost.ui.theme import configure_theme


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    configure_theme(root)
    if not ensure_data_directory(root):
        root.destroy()
        return 1
    configure_logging(log_path())
    root.title("BlogPilot · 智博日更")
    root.geometry("1040x740")
    root.minsize(900, 660)
    MainWindow(root, build_context())
    root.deiconify()
    root.mainloop()
    return 0
