from __future__ import annotations

from ctypes import Structure, byref, c_long, windll
import sys
import tkinter as tk
from tkinter import BooleanVar, StringVar, Toplevel, messagebox, ttk

from blogpost.application import ApplicationContext
from blogpost.config import AppConfig
from blogpost.paths import config_path
from blogpost.ui.theme import COLORS


def fit_dialog_geometry(
    parent: tuple[int, int, int, int],
    work_area: tuple[int, int, int, int],
    preferred: tuple[int, int] = (650, 760),
    margin: int = 16,
) -> tuple[int, int, int, int]:
    """Return width, height, x and y fully contained in the usable desktop."""
    parent_x, parent_y, parent_width, parent_height = parent
    left, top, right, bottom = work_area
    available_width = max(1, right - left - margin * 2)
    available_height = max(1, bottom - top - margin * 2)
    width = min(preferred[0], available_width)
    height = min(preferred[1], available_height)
    x = parent_x + (parent_width - width) // 2
    y = parent_y + (parent_height - height) // 2
    x = min(max(x, left + margin), right - margin - width)
    y = min(max(y, top + margin), bottom - margin - height)
    return width, height, x, y


class _Rect(Structure):
    _fields_ = (("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long))


class SettingsDialog(Toplevel):
    def __init__(self, master, context: ApplicationContext, on_saved):
        super().__init__(master)
        self.withdraw()
        self.context = context
        self.on_saved = on_saved
        self.title("设置")
        self.configure(background=COLORS["surface"])
        self.transient(master)
        self.resizable(True, True)

        cfg = context.config
        self._saved_api_key, self._api_key_read_error = self._read_saved_api_key()
        self.vars = {
            "api_base_url": StringVar(value=cfg.api_base_url),
            "model": StringVar(value=cfg.model),
            "api_key": StringVar(value=self._saved_api_key),
            "dry_run": BooleanVar(value=cfg.dry_run),
            "show_key": BooleanVar(value=False),
        }
        self.api_key_status = StringVar(value=self._api_key_status_text())
        self._build()
        self.update_idletasks()
        self._place_in_work_area()
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _build(self) -> None:
        shell = ttk.Frame(self, style="Surface.TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Surface.TFrame", padding=(30, 24, 30, 18))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="设置", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="配置全局大模型服务和发布安全模式；账号信息在主界面单独管理",
            style="DialogText.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        body = ttk.Frame(shell, style="Surface.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            body,
            background=COLORS["surface"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scroll_content = ttk.Frame(self.canvas, style="Surface.TFrame", padding=(30, 0, 30, 12))
        self.scroll_content.columnconfigure(0, weight=1)
        self.content_window = self.canvas.create_window((0, 0), anchor="nw", window=self.scroll_content)
        self.scroll_content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<MouseWheel>", self._on_mousewheel)

        api_card = ttk.Frame(self.scroll_content, style="Card.TFrame", padding=(20, 17))
        api_card.grid(row=0, column=0, sticky="ew")
        api_card.columnconfigure(0, weight=1)
        ttk.Label(api_card, text="大模型服务", style="CardValue.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            api_card,
            text="使用 DeepSeek 的 OpenAI 格式；Anthropic 地址仅供 Claude Code 等工具使用",
            style="CardDetail.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))
        self._field(api_card, 2, "API Base URL（OpenAI 格式）", "api_base_url")
        self._field(api_card, 4, "模型名称", "model")

        ttk.Label(api_card, text="API Key", style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 6))
        key_row = ttk.Frame(api_card, style="Surface.TFrame")
        key_row.grid(row=7, column=0, sticky="ew")
        key_row.columnconfigure(0, weight=1)
        self.key_entry = ttk.Entry(
            key_row,
            textvariable=self.vars["api_key"],
            show="•",
            style="Modern.TEntry",
        )
        self.key_entry.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            key_row,
            text="显示",
            variable=self.vars["show_key"],
            style="Modern.TCheckbutton",
            command=self._toggle_key,
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            api_card,
            textvariable=self.api_key_status,
            style="CardDetail.TLabel",
        ).grid(row=8, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            api_card,
            text="输入框留空不会删除密钥；如需更换，直接输入新 Key 后保存",
            style="CardDetail.TLabel",
        ).grid(row=9, column=0, sticky="w", pady=(3, 0))

        publish_card = ttk.Frame(self.scroll_content, style="Card.TFrame", padding=(20, 17))
        publish_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        publish_card.columnconfigure(0, weight=1)
        ttk.Label(publish_card, text="全局发布安全", style="CardValue.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            publish_card,
            text="发布时间、主页、文章分类和内容方向由每个账号独立配置",
            style="CardDetail.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        ttk.Checkbutton(
            publish_card,
            text="启用安全试运行（填写编辑器，但不点击最终发布）",
            variable=self.vars["dry_run"],
            style="Modern.TCheckbutton",
        ).grid(row=2, column=0, sticky="w")

        footer = ttk.Frame(shell, style="Surface.TFrame", padding=(30, 14, 30, 20))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="取消", style="Secondary.TButton", command=self.destroy).grid(row=0, column=1)
        ttk.Button(footer, text="保存设置", style="Primary.TButton", command=self._save).grid(
            row=0, column=2, padx=(10, 0)
        )

    def _field(self, parent: ttk.Frame, row: int, label: str, name: str) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
            pady=(0 if row == 2 else 12, 6),
        )
        ttk.Entry(parent, textvariable=self.vars[name], style="Modern.TEntry").grid(
            row=row + 1,
            column=0,
            sticky="ew",
        )

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after_idle(self._update_scrollbar)

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.content_window, width=event.width)
        self.after_idle(self._update_scrollbar)

    def _update_scrollbar(self) -> None:
        if not self.winfo_exists():
            return
        needs_scroll = self.canvas.bbox("all") and self.scroll_content.winfo_reqheight() > self.canvas.winfo_height()
        if needs_scroll:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()

    def _on_mousewheel(self, event) -> None:
        if self.canvas.bbox("all") and self.scroll_content.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _toggle_key(self) -> None:
        self.key_entry.configure(show="" if self.vars["show_key"].get() else "•")

    def _api_key_status_text(self) -> str:
        if self._api_key_read_error:
            return "无法读取已保存的 API Key，请输入新 Key 后重新保存"
        if self._saved_api_key:
            return "✓ API Key 已加密保存；上方显示为掩码，点击“显示”可查看"
        return "尚未保存 API Key"

    def _read_saved_api_key(self) -> tuple[str, bool]:
        try:
            return self.context.secrets.get_api_key() or "", False
        except Exception:
            return "", True

    def _work_area(self) -> tuple[int, int, int, int]:
        if sys.platform == "win32":
            rect = _Rect()
            if windll.user32.SystemParametersInfoW(0x0030, 0, byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _place_in_work_area(self) -> None:
        parent = (
            self.master.winfo_rootx(),
            self.master.winfo_rooty(),
            self.master.winfo_width(),
            self.master.winfo_height(),
        )
        width, height, x, y = fit_dialog_geometry(parent, self._work_area())
        self.minsize(min(560, width), min(440, height))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _save(self) -> None:
        try:
            old = self.context.config
            cfg = AppConfig(
                history_dir=old.history_dir,
                generated_dir=old.generated_dir,
                schedule_time=old.schedule_time,
                api_base_url=self.vars["api_base_url"].get().strip(),
                model=self.vars["model"].get().strip(),
                category=old.category,
                profile_url=old.profile_url,
                dry_run=self.vars["dry_run"].get(),
                min_chinese_chars=old.min_chinese_chars,
                target_min_chars=old.target_min_chars,
                target_max_chars=old.target_max_chars,
                title_similarity_threshold=old.title_similarity_threshold,
                content_similarity_threshold=old.content_similarity_threshold,
            )
            cfg.validate_for_run()
            cfg.save(config_path())
            api_key = self.vars["api_key"].get().strip()
            if api_key:
                self.context.secrets.set_api_key(api_key)
            self.context.config = cfg
            self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("设置无效", str(exc), parent=self)
