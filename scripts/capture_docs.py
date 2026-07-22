"""Capture privacy-safe documentation screenshots without opening a browser."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import tkinter as tk

from PIL import ImageGrab


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA_DIR = PROJECT_ROOT / "build" / "docs-demo-data"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"

# This must be set before any BlogPilot module imports blogpost.paths.
os.environ["BLOGPILOT_DATA_DIR"] = str(DEMO_DATA_DIR)

from blogpost.application import build_context  # noqa: E402
from blogpost.ui.help_dialog import HelpDialog  # noqa: E402
from blogpost.ui.main_window import MainWindow  # noqa: E402
from blogpost.ui.theme import configure_theme  # noqa: E402


def _capture(window: tk.Misc, path: Path) -> None:
    window.update_idletasks()
    window.update()
    left = window.winfo_rootx()
    top = window.winfo_rooty()
    right = left + window.winfo_width()
    bottom = top + window.winfo_height()
    ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(path)


def main() -> int:
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)
    DEMO_DATA_DIR.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    root.withdraw()
    configure_theme(root)
    root.title("BlogPilot · 智博日更")
    root.geometry("1040x740+40+40")
    root.minsize(900, 660)

    context = build_context()
    default_account = context.account()
    context.repository.save_account(
        replace(
            default_account,
            display_name="示例账号",
            profile_url="",
            keywords="AI Agent、工程实践",
        )
    )
    MainWindow(root, context)
    root.deiconify()
    root.update()
    root.after(450, root.quit)
    root.mainloop()
    _capture(root, OUTPUT_DIR / "main-window-guide.png")

    dialog = HelpDialog(root)
    dialog.update()
    dialog.after(350, dialog.quit)
    dialog.mainloop()
    _capture(dialog, OUTPUT_DIR / "help-dialog-guide.png")
    dialog.destroy()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
