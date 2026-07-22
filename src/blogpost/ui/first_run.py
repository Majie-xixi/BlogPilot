from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from blogpost.paths import configured_data_dir, initialize_data_dir, save_data_dir


def ensure_data_directory(parent) -> bool:
    """Require a persistent data directory before application services start."""
    configured = configured_data_dir()
    if configured is not None:
        try:
            initialize_data_dir(configured)
            return True
        except OSError as exc:
            messagebox.showerror(
                "数据目录不可用",
                f"无法使用当前数据目录：\n{configured}\n\n{exc}",
                parent=parent,
            )
            return False

    documents = Path.home() / "Documents"
    initial_dir = documents if documents.is_dir() else Path.home()
    selected = filedialog.askdirectory(
        title="选择 BlogPilot 数据目录（文章、账号和运行记录）",
        initialdir=str(initial_dir),
        mustexist=False,
        parent=parent,
    )
    if not selected:
        return False
    try:
        save_data_dir(Path(selected))
        return True
    except OSError as exc:
        messagebox.showerror(
            "无法创建数据目录",
            f"请换一个有写入权限的目录。\n\n{exc}",
            parent=parent,
        )
        return False
