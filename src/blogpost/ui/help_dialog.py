from __future__ import annotations

from ctypes import Structure, byref, c_long, windll
from dataclasses import dataclass
import sys
import tkinter as tk
from tkinter import ttk

from blogpost.ui.settings_dialog import fit_dialog_geometry
from blogpost.ui.theme import COLORS, FONT
from blogpost.ui.widgets import RoundedButton, RoundedPanel


@dataclass(frozen=True, slots=True)
class HelpStep:
    number: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ButtonGuideItem:
    label: str
    description: str


HELP_STEPS = (
    HelpStep(
        "01",
        "选择专用数据目录",
        "第一次启动时选择一个空间充足、容易备份的数据目录。账号配置、文章、运行历史和浏览器登录会话都保存在这里，卸载软件不会删除它。",
    ),
    HelpStep(
        "02",
        "配置大模型",
        "打开“全局设置”，填写 API Base URL、模型名称和 API Key。第一次使用请保持“安全试运行”开启，先检查生成质量和网页填写结果。",
    ),
    HelpStep(
        "03",
        "添加发布账号",
        "打开“账号管理”，填写 51CTO 主页、分类、发布时间、内容方向和关键词。保存后，顶部账号名称用于切换当前操作对象。",
    ),
    HelpStep(
        "04",
        "完成自动发布登录",
        "切换到每个账号，分别点击“自动发布登录”，在弹出的独立 Chrome 窗口中登录一次。BlogPilot 会隔离各账号会话，不会保存 51CTO 密码。",
    ),
    HelpStep(
        "05",
        "先试运行，再真实发布",
        "点击“立即生成并发布”完成第一次安全试运行。确认文章、分类和编辑器内容无误后，再到“全局设置”关闭安全试运行，启用真实发布。",
    ),
    HelpStep(
        "06",
        "启用每日任务",
        "点击“更新每日任务”，按各账号设定的时间自动执行。发布失败时可用“重新发布最近文章”重试已保存内容，不会再次调用大模型生成。",
    ),
)


BUTTON_GUIDE = (
    ButtonGuideItem("立即生成并发布", "为当前账号选题、生成、检查、保存并按当前模式发布。"),
    ButtonGuideItem("批量依次发布", "选择多个已启用账号，分别生成不同文章并依次处理。"),
    ButtonGuideItem("打开 51CTO", "在普通浏览器中查看当前账号主页。"),
    ButtonGuideItem("自动发布登录", "打开当前账号专用的自动化窗口并建立登录会话。"),
    ButtonGuideItem("更新每日任务", "安装或更新 Windows 每日计划任务。"),
    ButtonGuideItem("打开最近文章", "打开当前账号最后一次保存的 Markdown 文章。"),
    ButtonGuideItem("打开文章目录", "查看当前账号生成文章所在的本地目录。"),
    ButtonGuideItem("重新发布最近文章", "重发已保存文章，不重新生成，也不再次消耗大模型额度。"),
)


class _Rect(Structure):
    _fields_ = (("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long))


class HelpDialog(tk.Toplevel):
    """Beginner-oriented, read-only guide using the app's visual language."""

    def __init__(self, master):
        super().__init__(master)
        self.withdraw()
        self.title("使用说明")
        self.configure(background=COLORS["surface"])
        self.transient(master)
        self.resizable(True, True)
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

        header = ttk.Frame(shell, style="Surface.TFrame", padding=(30, 24, 30, 16))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="使用说明", style="DialogTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="从首次配置到自动发布，按下面的顺序完成即可",
            style="DialogText.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        RoundedButton(
            header,
            text="关闭",
            command=self.destroy,
            variant="secondary",
            outer=COLORS["surface"],
        ).grid(row=0, column=1, rowspan=2, sticky="e")

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

        self.scroll_content = ttk.Frame(
            self.canvas,
            style="Surface.TFrame",
            padding=(30, 0, 30, 28),
        )
        self.scroll_content.columnconfigure(0, weight=1)
        self.content_window = self.canvas.create_window(
            (0, 0), anchor="nw", window=self.scroll_content
        )
        self.scroll_content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Escape>", lambda _event: self.destroy())

        ttk.Label(
            self.scroll_content,
            text="第一次使用",
            style="Field.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        for row, step in enumerate(HELP_STEPS, start=1):
            self._step_card(self.scroll_content, row, step)

        guide_row = len(HELP_STEPS) + 1
        ttk.Label(
            self.scroll_content,
            text="按钮速查",
            style="Field.TLabel",
        ).grid(row=guide_row, column=0, sticky="w", pady=(22, 10))
        guide_panel = RoundedPanel(
            self.scroll_content,
            radius=10,
            padding=(18, 14),
            fill=COLORS["surface_alt"],
            outer=COLORS["surface"],
        )
        guide_panel.grid(row=guide_row + 1, column=0, sticky="ew")
        guide = guide_panel.content
        guide.columnconfigure(1, weight=1)
        for row, item in enumerate(BUTTON_GUIDE):
            tk.Label(
                guide,
                text=item.label,
                background=COLORS["surface_alt"],
                foreground=COLORS["text"],
                font=(FONT, 9, "bold"),
                anchor="w",
            ).grid(row=row, column=0, sticky="nw", padx=(0, 18), pady=5)
            tk.Label(
                guide,
                text=item.description,
                background=COLORS["surface_alt"],
                foreground=COLORS["muted"],
                font=(FONT, 9),
                anchor="w",
                justify="left",
                wraplength=430,
            ).grid(row=row, column=1, sticky="ew", pady=5)

        safety_row = guide_row + 2
        safety_panel = RoundedPanel(
            self.scroll_content,
            radius=10,
            padding=(18, 14),
            fill=COLORS["primary_soft"],
            outer=COLORS["surface"],
        )
        safety_panel.grid(row=safety_row, column=0, sticky="ew", pady=(14, 0))
        safety = safety_panel.content
        safety.columnconfigure(0, weight=1)
        tk.Label(
            safety,
            text="安全提示",
            background=COLORS["primary_soft"],
            foreground=COLORS["primary_hover"],
            font=(FONT, 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            safety,
            text="API Key 使用 Windows DPAPI 加密保存在你选择的数据目录中；遇到验证码、登录失效或页面结构异常时会停止，不会反复提交。",
            background=COLORS["primary_soft"],
            foreground=COLORS["text"],
            font=(FONT, 9),
            justify="left",
            wraplength=590,
        ).grid(row=1, column=0, sticky="ew", pady=(5, 0))

    def _step_card(self, parent, row: int, step: HelpStep) -> None:
        panel = RoundedPanel(
            parent,
            radius=10,
            padding=(16, 13),
            fill=COLORS["surface_alt"],
            outer=COLORS["surface"],
        )
        panel.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        card = panel.content
        card.columnconfigure(1, weight=1)
        tk.Label(
            card,
            text=step.number,
            background=COLORS["primary_soft"],
            foreground=COLORS["primary"],
            font=(FONT, 9, "bold"),
            padx=9,
            pady=5,
        ).grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 13))
        tk.Label(
            card,
            text=step.title,
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            font=(FONT, 10, "bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")
        tk.Label(
            card,
            text=step.description,
            background=COLORS["surface_alt"],
            foreground=COLORS["muted"],
            font=(FONT, 9),
            justify="left",
            anchor="w",
            wraplength=570,
        ).grid(row=1, column=1, sticky="ew", pady=(4, 0))

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after_idle(self._update_scrollbar)

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.content_window, width=event.width)
        self.after_idle(self._update_scrollbar)

    def _update_scrollbar(self) -> None:
        if not self.winfo_exists():
            return
        needs_scroll = (
            self.canvas.bbox("all")
            and self.scroll_content.winfo_reqheight() > self.canvas.winfo_height()
        )
        if needs_scroll:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()

    def _on_mousewheel(self, event) -> None:
        if self.canvas.bbox("all") and self.scroll_content.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

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
        width, height, x, y = fit_dialog_geometry(
            parent,
            self._work_area(),
            preferred=(720, 760),
        )
        self.minsize(min(620, width), min(480, height))
        self.geometry(f"{width}x{height}+{x}+{y}")
