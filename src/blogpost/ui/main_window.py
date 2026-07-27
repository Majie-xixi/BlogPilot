from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import os
from pathlib import Path
from queue import Empty, Queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import time
import webbrowser

from blogpost.application import ApplicationContext
from blogpost.domain import Account, DEFAULT_ACCOUNT_ID, PublishResult, RunStatus, Trigger
from blogpost.publishers.cto51_profile import ProfileSnapshot
from blogpost.ui.account_dialog import (
    AccountManagerDialog,
    BatchPublishDialog,
    is_generic_account_name,
)
from blogpost.ui.help_dialog import HelpDialog
from blogpost.ui.settings_dialog import SettingsDialog
from blogpost.ui.theme import COLORS, FONT
from blogpost.ui.widgets import RoundedButton, RoundedPanel, RoundedProgressBar


STATUS_TEXT = {
    RunStatus.QUEUED: "等待中",
    RunStatus.PLANNING: "正在选题",
    RunStatus.GENERATING: "正在生成",
    RunStatus.VALIDATING: "正在检查",
    RunStatus.SAVING: "正在保存",
    RunStatus.PUBLISHING: "正在发布",
    RunStatus.PUBLISHED: "发布成功",
    RunStatus.SKIPPED: "已跳过",
    RunStatus.NEEDS_REVIEW: "需要人工检查",
    RunStatus.FAILED: "执行失败",
    RunStatus.UNKNOWN: "发布结果待确认",
}

STATUS_PROGRESS = {
    RunStatus.QUEUED: 5,
    RunStatus.PLANNING: 15,
    RunStatus.GENERATING: 45,
    RunStatus.VALIDATING: 65,
    RunStatus.SAVING: 80,
    RunStatus.PUBLISHING: 92,
    RunStatus.PUBLISHED: 100,
    RunStatus.SKIPPED: 100,
    RunStatus.NEEDS_REVIEW: 100,
    RunStatus.FAILED: 100,
    RunStatus.UNKNOWN: 100,
}

TRIGGER_TEXT = {
    Trigger.MANUAL: "手动",
    Trigger.SCHEDULED: "定时",
    Trigger.SYNCED: "线上同步",
}


def format_schedule_status(status: str, time_text: str) -> tuple[str, str]:
    status = status.strip()
    if not status or status == "Missing":
        return "尚未安装", f"配置时间 {time_text} · 点击下方按钮安装"
    if status == "Invalid|ExecutableMissing":
        return "任务需要更新", "启动文件不存在 · 点击“更新每日任务”修复"
    if status == "Invalid|ActionMismatch":
        return "任务需要更新", "启动命令已经过期 · 点击“更新每日任务”修复"
    if status.startswith("Failed|"):
        result = status.partition("|")[2]
        return "上次运行失败", f"错误码 {result} · 点击“更新每日任务”修复"
    if status.startswith("检查失败"):
        return f"配置时间 {time_text}", status
    state_text = {
        "Ready": "就绪",
        "Running": "正在运行",
        "Disabled": "已禁用",
        "Queued": "等待运行",
    }.get(status, status)
    return f"每天 {time_text}", f"Windows 计划任务已安装 · {state_text}"


def parse_persisted_log_line(line: str) -> tuple[str, str, str]:
    """Convert a plain file log into the same visual entry used for live logs."""
    match = re.match(
        r"^\d{4}-\d{2}-\d{2}T(?P<time>\d{2}:\d{2}:\d{2})\s+"
        r"(?P<level>[A-Z]+)\s+\S+\s+(?P<body>.*)$",
        line.strip(),
    )
    if not match:
        return "--:--:--", "info", line.strip()

    body = match.group("body")
    status_match = re.search(r"(?:pipeline\s+)?status=([a-z_]+)", body)
    status_value = status_match.group(1) if status_match else ""
    message = body.partition(" message=")[2] if " message=" in body else body
    if "pipeline started" in body:
        trigger = "手动" if "trigger=manual" in body else "定时"
        message = f"任务已启动 · {trigger}触发"
    elif status_value:
        try:
            status = RunStatus(status_value)
            message = f"{STATUS_TEXT.get(status, status.value)}：{message}"
        except ValueError:
            pass

    if match.group("level") in {"ERROR", "CRITICAL"} or status_value == RunStatus.FAILED.value:
        visual_level = "error"
    elif status_value in {RunStatus.NEEDS_REVIEW.value, RunStatus.UNKNOWN.value}:
        visual_level = "warning"
    elif status_value in {RunStatus.PUBLISHED.value, RunStatus.SKIPPED.value}:
        visual_level = "success"
    else:
        visual_level = "info"
    return match.group("time"), visual_level, message


class MainWindow:
    def __init__(self, root: tk.Tk, context: ApplicationContext):
        self.root = root
        self.context = context
        self.queue: Queue[tuple] = Queue()
        self.running = False
        self.profile_snapshot: ProfileSnapshot | None = None
        self.status_refreshing = False
        self.status_refresh_generation = 0
        self.account_map: dict[str, Account] = {}
        self.current_account_id = DEFAULT_ACCOUNT_ID
        self.account_popup: tk.Toplevel | None = None
        self.login_sync_generation = 0
        self.batch_progress_positions: dict[str, int] = {}
        self.batch_progress_total = 1
        self._build()
        self._reload_accounts(DEFAULT_ACCOUNT_ID)
        self.refresh()
        self._show_empty_log()
        self.root.after(150, self._drain_queue)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        page = ttk.Frame(self.root, style="Page.TFrame", padding=(36, 24, 36, 16))
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)

        header = ttk.Frame(page, style="Page.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        title_block = ttk.Frame(header, style="Page.TFrame")
        title_block.grid(row=0, column=0, sticky="w")
        ttk.Label(title_block, text="BlogPilot · 智博日更", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_block,
            text="每天生成一篇原创 AI 技术文章，并自动发布到 51CTO",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        account_controls = ttk.Frame(header, style="Page.TFrame")
        account_controls.grid(row=0, column=1, rowspan=2, sticky="e")
        self.account_var = tk.StringVar()
        self.account_selector = RoundedButton(
            account_controls,
            textvariable=self.account_var,
            command=self._toggle_account_popup,
            variant="identity",
            min_width=160,
            height=34,
            radius=7,
            font=(FONT, 10),
            anchor="w",
            padding_x=13,
            outer=COLORS["page"],
            icon="account",
            chevron=True,
        )
        self.account_selector.grid(row=0, column=0, sticky="ew")
        tk.Frame(
            account_controls,
            width=1,
            height=22,
            background=COLORS["border"],
        ).grid(row=0, column=1, padx=(10, 2))
        RoundedButton(
            account_controls,
            text="使用说明",
            command=self.open_help,
            variant="secondary",
            outer=COLORS["page"],
        ).grid(row=0, column=2, padx=(8, 0))
        RoundedButton(
            account_controls,
            text="账号管理",
            command=self.open_account_manager,
            variant="secondary",
            outer=COLORS["page"],
        ).grid(row=0, column=3, padx=(8, 0))
        RoundedButton(
            account_controls,
            text="全局设置",
            command=self.open_settings,
            variant="secondary",
            outer=COLORS["page"],
        ).grid(
            row=0, column=4, padx=(8, 0)
        )

        stats = ttk.Frame(page, style="Page.TFrame")
        stats.grid(row=1, column=0, sticky="ew", pady=(18, 12))
        for column in range(3):
            stats.columnconfigure(column, weight=1, uniform="stats")
        self.today_value_var = tk.StringVar(value="尚未发布")
        self.today_detail_var = tk.StringVar(value="正在读取今日记录")
        self.schedule_value_var = tk.StringVar(value="每天 10:00")
        self.schedule_detail_var = tk.StringVar(value="错过时间后会自动补跑")
        self.mode_value_var = tk.StringVar(value="安全试运行")
        self.mode_detail_var = tk.StringVar(value="填写编辑器，不点击发布")
        self._status_card(stats, 0, "今日状态", self.today_value_var, self.today_detail_var, COLORS["success"])
        self._status_card(stats, 1, "自动计划", self.schedule_value_var, self.schedule_detail_var, COLORS["primary"])
        self._status_card(stats, 2, "发布模式", self.mode_value_var, self.mode_detail_var, COLORS["warning"])

        hero_panel = RoundedPanel(page, radius=12, padding=(18, 14))
        hero_panel.grid(row=2, column=0, sticky="ew")
        hero = hero_panel.content
        hero.columnconfigure(0, weight=1)
        self.hero_title_var = tk.StringVar(value="准备生成今天的 AI 技术博文")
        ttk.Label(hero, textvariable=self.hero_title_var, style="HeroTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress_var = tk.StringVar(value="准备就绪 · 点击右侧按钮即可开始")
        ttk.Label(hero, textvariable=self.progress_var, style="HeroText.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        hero_actions = ttk.Frame(hero, style="Surface.TFrame")
        hero_actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(24, 0))
        self.batch_button = RoundedButton(
            hero_actions,
            text="批量依次发布",
            command=self.open_batch_publish,
            variant="secondary",
            height=36,
            outer=COLORS["surface"],
        )
        self.batch_button.grid(row=0, column=0, sticky="ew")
        self.run_button = RoundedButton(
            hero_actions,
            text="立即生成并发布 →",
            command=self.run_now,
            variant="primary",
            min_width=150,
            height=36,
            outer=COLORS["surface"],
        )
        self.run_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.progress_frame = ttk.Frame(hero, style="Surface.TFrame")
        self.progress_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.progress_frame.columnconfigure(0, weight=1)
        self.progressbar = RoundedProgressBar(
            self.progress_frame,
            value=0,
            maximum=100,
            height=4,
            outer=COLORS["surface"],
        )
        self.progressbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.progress_step_var = tk.StringVar(value="")
        self.progress_pct_var = tk.StringVar(value="0%")
        ttk.Label(
            self.progress_frame,
            textvariable=self.progress_step_var,
            style="HeroText.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(
            self.progress_frame,
            textvariable=self.progress_pct_var,
            style="HeroText.TLabel",
        ).grid(row=1, column=1, sticky="e", pady=(5, 0))
        self.progress_frame.grid_remove()

        actions = ttk.Frame(page, style="Page.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(14, 14))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, text="常用操作", style="Subtitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        action_buttons = ttk.Frame(actions, style="Page.TFrame")
        action_buttons.grid(row=1, column=0, sticky="ew")
        for column in range(6):
            action_buttons.columnconfigure(column, weight=1, uniform="actions")
        for column, text, command in (
            (0, "打开 51CTO", self.open_profile),
            (1, "自动发布登录", self.open_login),
            (2, "更新每日任务", self.install_schedule),
            (3, "打开最近文章", self.open_latest_article),
            (4, "打开文章目录", self.open_generated_dir),
            (5, "重新发布最近文章", self.retry_latest_article),
        ):
            button = RoundedButton(
                action_buttons,
                text=text,
                command=command,
                variant="secondary",
                outer=COLORS["page"],
            )
            button.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 4, 0 if column == 5 else 4),
            )
            if text == "打开最近文章":
                self.latest_article_button = button
            elif text == "重新发布最近文章":
                self.retry_button = button
            elif text == "自动发布登录":
                self.login_button = button

        section = ttk.Frame(page, style="Page.TFrame")
        section.grid(row=4, column=0, sticky="ew", pady=(0, 7))
        section.columnconfigure(0, weight=1)
        self.detail_title_var = tk.StringVar(value="运行日志")
        self.detail_hint_var = tk.StringVar(value="生成、检查、保存和发布步骤会实时显示")
        ttk.Label(section, textvariable=self.detail_title_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(section, textvariable=self.detail_hint_var, style="Subtitle.TLabel").grid(
            row=0, column=1, sticky="e", padx=(0, 12)
        )
        self.detail_toggle_button = RoundedButton(
            section,
            text="查看历史记录",
            variant="link",
            height=28,
            command=self._toggle_detail_view,
            outer=COLORS["page"],
        )
        self.detail_toggle_button.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self.clear_log_button = RoundedButton(
            section,
            text="清空日志",
            variant="link",
            height=28,
            command=self._clear_log_and_show_empty,
            outer=COLORS["page"],
        )
        self.clear_log_button.grid(row=0, column=3, sticky="e")

        detail_stack = ttk.Frame(page, style="Page.TFrame")
        detail_stack.grid(row=5, column=0, sticky="nsew")
        detail_stack.columnconfigure(0, weight=1)
        detail_stack.rowconfigure(0, weight=1)
        self.log_view = RoundedPanel(detail_stack, radius=10, padding=(1, 1))
        self.history_view = RoundedPanel(detail_stack, radius=10, padding=(1, 1))
        self.log_view.grid(row=0, column=0, sticky="nsew")
        self.history_view.grid(row=0, column=0, sticky="nsew")
        self.history_view.grid_remove()
        self.detail_view = "log"

        log_content = self.log_view.content
        log_content.columnconfigure(0, weight=1)
        log_content.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_content,
            wrap="word",
            state="disabled",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            selectbackground=COLORS["primary_soft"],
            relief="flat",
            borderwidth=0,
            font=("Cascadia Mono", 9),
            padx=14,
            pady=12,
            height=8,
        )
        log_scrollbar = ttk.Scrollbar(log_content, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.tag_configure("success", foreground=COLORS["success"])
        self.log_text.tag_configure("warning", foreground=COLORS["warning"])
        self.log_text.tag_configure("error", foreground=COLORS["danger"])
        self.log_text.tag_configure("muted", foreground=COLORS["muted"])
        self.log_text.tag_configure("time", foreground=COLORS["muted"])
        self.log_text.tag_configure("info_badge", foreground="#0369A1", font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("success_badge", foreground=COLORS["success"], font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("warning_badge", foreground=COLORS["warning"], font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("error_badge", foreground=COLORS["danger"], font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("keyword_51cto", foreground="#0369A1", font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("keyword_deepseek", foreground="#7C3AED", font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_configure("keyword_markdown", foreground="#A16207", font=("Cascadia Mono", 9, "bold"))

        history_content = self.history_view.content
        history_content.columnconfigure(0, weight=1)
        history_content.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            history_content,
            columns=("time", "trigger", "status", "message"),
            show="headings",
            selectmode="browse",
        )
        for name, text, width, stretch in (
            ("time", "时间", 155, False),
            ("trigger", "触发方式", 90, False),
            ("status", "状态", 120, False),
            ("message", "说明", 470, True),
        ):
            self.tree.heading(name, text=text)
            self.tree.column(name, width=width, minwidth=width, stretch=stretch, anchor="w")
        self.history_scrollbar = ttk.Scrollbar(history_content, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.history_scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.history_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("published", foreground=COLORS["success"])
        self.tree.tag_configure("failed", foreground=COLORS["danger"])
        self.tree.tag_configure("review", foreground=COLORS["warning"])

        footer = tk.Frame(page, background=COLORS["page"])
        footer.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        tk.Label(footer, text="●", foreground=COLORS["success"], background=COLORS["page"], font=(FONT, 8)).pack(side="left")
        tk.Label(
            footer,
            text="安全保护已开启：验证码、登录失效或页面变化时会停止，不会重复提交",
            foreground=COLORS["muted"],
            background=COLORS["page"],
            font=(FONT, 9),
        ).pack(side="left", padx=(7, 0))

    def _status_card(self, parent, column, caption, value_var, detail_var, dot_color) -> None:
        panel = RoundedPanel(parent, radius=12, padding=(15, 13))
        panel.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 6, 0 if column == 2 else 6),
        )
        card = panel.content
        card.columnconfigure(1, weight=1)
        tk.Label(card, text="●", foreground=dot_color, background=COLORS["surface"], font=(FONT, 8)).grid(
            row=0, column=0, sticky="w", padx=(0, 7)
        )
        ttk.Label(card, text=caption, style="CardCaption.TLabel").grid(row=0, column=1, sticky="w")
        value_style = (
            "CardSuccessValue.TLabel"
            if caption == "今日状态"
            else "CardWarningValue.TLabel"
            if caption == "发布模式"
            else "CardValue.TLabel"
        )
        ttk.Label(card, textvariable=value_var, style=value_style).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 3)
        )
        ttk.Label(card, textvariable=detail_var, style="CardDetail.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

    @property
    def current_account(self) -> Account:
        return self.account_map.get(self.current_account_id) or self.context.account()

    def _reload_accounts(self, selected_id: str | None = None) -> None:
        accounts = self.context.accounts()
        self.account_map = {account.id: account for account in accounts}
        wanted = selected_id if selected_id in self.account_map else accounts[0].id
        self.current_account_id = wanted
        self._show_account_name(self.account_map[wanted])

    def _show_account_name(self, account: Account) -> None:
        self.account_var.set(account.display_name)

    def _select_account(self, account_id: str) -> None:
        if account_id not in self.account_map:
            return
        self.current_account_id = account_id
        self._show_account_name(self.account_map[account_id])
        self._close_account_popup()
        self.status_refresh_generation += 1
        self.status_refreshing = False
        self.profile_snapshot = None
        self._clear_log()
        self._show_empty_log()
        self._reset_progress_if_idle()
        self.refresh()

    def _toggle_account_popup(self) -> None:
        if self.account_popup is not None and self.account_popup.winfo_exists():
            self._close_account_popup()
            return
        popup = tk.Toplevel(self.root)
        self.account_popup = popup
        popup.overrideredirect(True)
        popup.configure(background=COLORS["border"])
        popup.transient(self.root)
        width = max(210, self.account_selector.winfo_width())
        height = 12 + len(self.account_map) * 44
        x = self.account_selector.winfo_rootx()
        y = self.account_selector.winfo_rooty() + self.account_selector.winfo_height() + 6
        popup.geometry(f"{width}x{height}+{x}+{y}")
        card = tk.Frame(
            popup,
            background=COLORS["surface"],
            highlightthickness=0,
            padx=5,
            pady=5,
        )
        card.pack(fill="both", expand=True)
        for account in self.context.accounts():
            selected = account.id == self.current_account_id
            prefix = "●" if selected else " "
            suffix = "" if account.enabled else "  · 已停用"
            button = RoundedButton(
                card,
                text=f"{prefix}  {account.display_name}{suffix}",
                command=lambda account_id=account.id: self._select_account(account_id),
                variant="toggle",
                selected=selected,
                anchor="w",
                padding_x=12,
                height=38,
                font=(FONT, 9, "bold" if selected else "normal"),
                outer=COLORS["surface"],
            )
            button.pack(fill="x")
        popup.bind("<Escape>", lambda _event: self._close_account_popup())
        popup.lift()
        popup.focus_force()

    def _close_account_popup(self) -> None:
        popup = self.account_popup
        self.account_popup = None
        if popup is not None and popup.winfo_exists():
            popup.destroy()

    def open_account_manager(self) -> None:
        AccountManagerDialog(self.root, self.context, self._account_saved)

    def open_help(self) -> None:
        HelpDialog(self.root)

    def _account_saved(self, account_id: str) -> None:
        self._reload_accounts(account_id)
        self.profile_snapshot = None
        self.refresh()

    def refresh(self) -> None:
        account = self.current_account
        cfg = self.context.config_for_account(account.id)
        self.schedule_value_var.set(f"配置时间 {account.schedule_time:%H:%M}")
        self.schedule_detail_var.set("正在检查 Windows 计划任务…")
        self._render_publication_status()
        if cfg.dry_run:
            self.mode_value_var.set("安全试运行")
            self.mode_detail_var.set("填写编辑器，不点击最终发布")
        else:
            self.mode_value_var.set("真实发布")
            self.mode_detail_var.set("检查通过后自动提交到 51CTO")

        self._refresh_history()
        self._start_runtime_status_refresh()

    def _refresh_history(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        account_id = self.current_account_id
        runs = list(self.context.repository.recent_runs(30, account_id))
        if len(runs) > 8:
            self.history_scrollbar.grid()
        else:
            self.history_scrollbar.grid_remove()
        for run in runs:
            tag = ""
            if run.status == RunStatus.PUBLISHED:
                tag = "published"
            elif run.status == RunStatus.FAILED:
                tag = "failed"
            elif run.status in {RunStatus.NEEDS_REVIEW, RunStatus.UNKNOWN}:
                tag = "review"
            self.tree.insert(
                "",
                "end",
                values=(
                    run.started_at.strftime("%Y-%m-%d %H:%M"),
                    TRIGGER_TEXT.get(run.trigger, run.trigger.value),
                    STATUS_TEXT.get(run.status, run.status.value),
                    run.error_summary or "—",
                ),
                tags=(tag,) if tag else (),
            )
        latest = self.context.repository.latest_article_path(account_id)
        self.latest_article_button.configure(state="normal" if latest and Path(latest).exists() else "disabled")
        self.retry_button.configure(
            state="normal" if latest and Path(latest).exists() and not self.running else "disabled"
        )

    def _render_publication_status(self, error: str | None = None) -> None:
        today = date.today()
        account = self.current_account
        local_published = self.context.repository.has_successful_publication(today, account.id)
        local_days = self.context.repository.count_successful_days(
            today.year,
            today.month,
            account.id,
        )
        snapshot = self.profile_snapshot
        if snapshot and snapshot.profile_url == account.profile_url.rstrip("/"):
            online_published = snapshot.has_publication_on(today)
            if online_published is True:
                self.today_value_var.set("已发布")
            elif online_published is False and local_published:
                self.today_value_var.set("状态待确认")
            elif online_published is False:
                self.today_value_var.set("尚未发布")
            else:
                self.today_value_var.set("已发布" if local_published else "状态未知")

            if snapshot.month_count is not None:
                remaining = max(0, account.monthly_target - snapshot.month_count)
                detail = f"本月 {snapshot.month_count}/{account.monthly_target} 篇 · 还差 {remaining} 篇"
            else:
                detail = f"51CTO 今日已核对 · 软件记录本月 {local_days} 天"
            if online_published is False and local_published:
                detail = "软件记录显示已发布，但 51CTO 主页暂未显示"
            self.today_detail_var.set(detail)
            return

        self.today_value_var.set("已发布" if local_published else "尚未发布")
        if self.status_refreshing:
            self.today_detail_var.set("正在同步 51CTO 公开主页…")
        elif error:
            self.today_detail_var.set(f"在线核对失败 · 仅软件记录本月 {local_days} 天")
        elif not account.profile_url:
            self.today_detail_var.set("未设置 51CTO 主页 · 仅显示软件记录")
        else:
            self.today_detail_var.set(f"仅软件记录：本月已发布 {local_days} 天")

    def _start_runtime_status_refresh(self, *, force: bool = False) -> None:
        if self.status_refreshing and not force:
            return
        self.status_refresh_generation += 1
        generation = self.status_refresh_generation
        account = self.current_account
        account_id = account.id
        profile_url = account.profile_url.rstrip("/")
        publisher = self.context.publisher_for_account(account_id)
        self.status_refreshing = True
        self._render_publication_status()

        def worker() -> None:
            snapshot = None
            profile_error = None
            try:
                if profile_url:
                    snapshot = publisher.profile_status()
            except Exception as exc:
                profile_error = str(exc)
            try:
                schedule_status = self.context.scheduler.status()
            except Exception as exc:
                schedule_status = f"检查失败：{exc}"
            self.queue.put(
                (
                    "runtime_status",
                    generation,
                    account_id,
                    profile_url,
                    snapshot,
                    profile_error,
                    schedule_status,
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_runtime_status(
        self,
        generation: int,
        account_id: str,
        profile_url: str,
        snapshot: ProfileSnapshot | None,
        profile_error: str | None,
        schedule_status: str,
    ) -> None:
        if generation != self.status_refresh_generation or account_id != self.current_account_id:
            return
        self.status_refreshing = False
        if profile_url == self.current_account.profile_url.rstrip("/"):
            self.profile_snapshot = snapshot
            if (
                snapshot
                and snapshot.display_name
                and is_generic_account_name(self.current_account.display_name)
            ):
                try:
                    saved = self.context.repository.save_account(
                        replace(self.current_account, display_name=snapshot.display_name)
                    )
                    self.account_map[account_id] = saved
                    self._show_account_name(saved)
                except Exception:
                    pass
            if (
                snapshot
                and snapshot.latest_published_at
                and snapshot.has_publication_on(date.today()) is True
            ):
                try:
                    self.context.repository.sync_online_publication(
                        snapshot.latest_published_at,
                        snapshot.latest_title,
                        snapshot.latest_url,
                        account_id,
                    )
                    self._refresh_history()
                except Exception as exc:
                    profile_error = f"历史同步失败：{exc}"
        self._render_publication_status(profile_error)

        time_text = self.current_account.schedule_time.strftime("%H:%M")
        value_text, detail_text = format_schedule_status(schedule_status, time_text)
        self.schedule_value_var.set(value_text)
        self.schedule_detail_var.set(detail_text)

    def _append_log(
        self,
        message: str,
        tag: str | None = None,
        *,
        timestamp: bool = True,
        time_text: str | None = None,
    ) -> None:
        self.log_text.configure(state="normal")
        if timestamp:
            level = tag if tag in {"success", "warning", "error"} else "info"
            badge = {
                "info": "INFO",
                "success": "DONE",
                "warning": "WARN",
                "error": "ERROR",
            }[level]
            display_time = time_text or f"{datetime.now():%H:%M:%S}"
            self.log_text.insert("end", display_time + " ", "time")
            self.log_text.insert("end", f"[{badge}] ", f"{level}_badge")
            self._insert_log_message(message.rstrip())
            self.log_text.insert("end", "\n")
        else:
            self.log_text.insert("end", message.rstrip() + "\n", tag or "")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _insert_log_message(self, message: str) -> None:
        keyword_tags = {
            "51CTO": "keyword_51cto",
            "DeepSeek": "keyword_deepseek",
            "Markdown": "keyword_markdown",
        }
        pattern = re.compile("(" + "|".join(map(re.escape, keyword_tags)) + ")")
        for part in pattern.split(message):
            if part:
                self.log_text.insert("end", part, keyword_tags.get(part, ""))

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _show_empty_log(self) -> None:
        self._append_log(
            "等待任务开始。本次生成、检查、保存和发布步骤会显示在这里。",
            "muted",
            timestamp=False,
        )

    def _clear_log_and_show_empty(self) -> None:
        self._clear_log()
        self._show_empty_log()

    def _show_progress(self, title: str, message: str, percent: int) -> None:
        value = max(0, min(100, int(percent)))
        self.hero_title_var.set(title)
        self.progress_var.set(message)
        self.progress_step_var.set(message)
        self.progress_pct_var.set(f"{value}%")
        self.progressbar.configure(mode="determinate", maximum=100, value=value)
        self.progress_frame.grid()

    def _update_stage_progress(self, status: RunStatus, message: str) -> None:
        percent = STATUS_PROGRESS.get(status, 5)
        self._show_progress(
            "正在生成今天的 AI 技术博文",
            f"{STATUS_TEXT.get(status, status.value)} · {message}",
            percent,
        )

    def _complete_progress(self, message: str) -> None:
        self.progressbar.configure(mode="determinate", maximum=100, value=100)
        self.progress_step_var.set(message)
        self.progress_pct_var.set("100%")

    def _reset_progress_if_idle(self) -> None:
        if self.running:
            return
        self.progress_frame.grid_remove()
        self.hero_title_var.set("准备生成今天的 AI 技术博文")
        self.progress_var.set("准备就绪 · 点击右侧按钮即可开始")
        self.run_button.configure(text="立即生成并发布 →")

    def _show_log_view(self) -> None:
        self.detail_view = "log"
        self.history_view.grid_remove()
        self.log_view.grid(row=0, column=0, sticky="nsew")
        self.detail_title_var.set("运行日志")
        self.detail_hint_var.set("生成、检查、保存和发布步骤会实时显示")
        self.detail_toggle_button.configure(text="查看历史记录")
        self.clear_log_button.grid()

    def _toggle_detail_view(self) -> None:
        if self.detail_view == "log":
            self.detail_view = "history"
            self.log_view.grid_remove()
            self.history_view.grid(row=0, column=0, sticky="nsew")
            self.detail_title_var.set("历史记录")
            self.detail_hint_var.set("最多显示最近 30 次运行结果")
            self.detail_toggle_button.configure(text="返回运行日志")
            self.clear_log_button.grid_remove()
        else:
            self._show_log_view()

    def open_settings(self) -> None:
        SettingsDialog(self.root, self.context, self.refresh)

    def run_now(self) -> None:
        if self.running:
            return
        allow = False
        online_published = (
            self.profile_snapshot.has_publication_on(date.today())
            if self.profile_snapshot
            and self.profile_snapshot.profile_url == self.current_account.profile_url.rstrip("/")
            else None
        )
        if self.context.repository.has_successful_publication(
            date.today(), self.current_account_id
        ) or online_published is True:
            allow = messagebox.askyesno("今天已经发布", "今天已有成功发布记录，仍要再生成并发布一篇吗？")
            if not allow:
                return
        try:
            pipeline = self.context.build_pipeline(self.current_account_id)
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        self.running = True
        self._clear_log()
        self._append_log("任务已启动，正在准备历史语料和选题。")
        self._show_log_view()
        self._show_progress("正在生成今天的 AI 技术博文", "正在准备历史语料和选题…", 5)
        self.run_button.configure(text="生成中…")
        self.run_button.configure(state="disabled")
        self.batch_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        threading.Thread(target=self._run_worker, args=(pipeline, allow), daemon=True).start()

    def retry_latest_article(self) -> None:
        if self.running:
            return
        account_id = self.current_account_id
        path_text = self.context.repository.latest_article_path(account_id)
        path = Path(path_text) if path_text else None
        if path is None or not path.exists():
            messagebox.showinfo("暂无文章", "没有找到可重新发布的已保存文章。")
            return
        if not messagebox.askyesno(
            "重新发布最近文章",
            f"将直接发布下面这篇文章，不会调用大模型重新生成：\n\n{path.name}\n\n是否继续？",
        ):
            return
        self.running = True
        self._clear_log()
        self._show_log_view()
        self._append_log(f"正在读取已保存文章：{path.name}")
        self._show_progress("正在重新发布已保存文章", "正在读取文章 · 不会重新生成", 10)
        self.run_button.configure(text="发布中…")
        self.run_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        self.batch_button.configure(state="disabled")
        threading.Thread(target=self._retry_worker, args=(account_id, path), daemon=True).start()

    def _retry_worker(self, account_id: str, path: Path) -> None:
        try:
            result = self.context.retry_saved_article(
                account_id,
                path,
                progress=lambda status, message: self.queue.put(("progress", status, message)),
            )
        except Exception as exc:
            result = PublishResult(RunStatus.FAILED, message=str(exc), article_path=str(path))
        self.queue.put(("done", result))

    def _run_worker(self, pipeline, allow: bool) -> None:
        result = pipeline.run(
            Trigger.MANUAL,
            allow_same_day=allow,
            progress=lambda status, message: self.queue.put(("progress", status, message)),
        )
        self.queue.put(("done", result))

    def open_batch_publish(self) -> None:
        if self.running:
            return
        accounts = self.context.accounts(enabled_only=True)
        if not accounts:
            messagebox.showinfo("没有启用账号", "请先在账号管理中启用至少一个账号。")
            return
        BatchPublishDialog(self.root, accounts, self._start_batch)

    def _start_batch(self, account_ids: list[str]) -> None:
        self.running = True
        self._clear_log()
        self._show_log_view()
        accounts = {
            account.id: account
            for account in self.context.accounts(enabled_only=True)
            if account.id in account_ids
        }
        ordered_names = [accounts[account_id].display_name for account_id in account_ids if account_id in accounts]
        self.batch_progress_positions = {
            account_name: index for index, account_name in enumerate(ordered_names)
        }
        self.batch_progress_total = max(1, len(ordered_names))
        self._show_progress(
            "正在依次处理多个账号",
            f"批量任务已启动 · 共 {len(account_ids)} 个账号",
            0,
        )
        self.run_button.configure(text="处理中…")
        self.run_button.configure(state="disabled")
        self.batch_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        threading.Thread(target=self._batch_worker, args=(account_ids,), daemon=True).start()

    def _batch_worker(self, account_ids: list[str]) -> None:
        results = self.context.run_accounts(
            account_ids,
            Trigger.MANUAL,
            progress=lambda account, status, message: self.queue.put(
                ("batch_progress", account.display_name, status, message)
            ),
        )
        self.queue.put(("batch_done", results))

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self.queue.get_nowait()
                if event[0] == "progress":
                    _, status, message = event
                    self._update_stage_progress(status, message)
                    tag = "error" if status == RunStatus.FAILED else "warning" if status in {RunStatus.NEEDS_REVIEW, RunStatus.UNKNOWN} else "success" if status == RunStatus.PUBLISHED else "info"
                    self._append_log(f"{STATUS_TEXT.get(status, status.value)}：{message}", tag)
                elif event[0] == "batch_progress":
                    _, account_name, status, message = event
                    index = self.batch_progress_positions.get(account_name, 0)
                    stage = STATUS_PROGRESS.get(status, 5) / 100
                    percent = round(
                        ((index + stage) / max(1, self.batch_progress_total)) * 100
                    )
                    self._show_progress(
                        "正在依次处理多个账号",
                        f"{account_name} · {STATUS_TEXT.get(status, status.value)} · {message}",
                        percent,
                    )
                    tag = "error" if status == RunStatus.FAILED else "warning" if status in {RunStatus.NEEDS_REVIEW, RunStatus.UNKNOWN} else "success" if status == RunStatus.PUBLISHED else "info"
                    self._append_log(
                        f"[{account_name}] {STATUS_TEXT.get(status, status.value)}：{message}",
                        tag,
                    )
                elif event[0] == "done":
                    self._finish_run(event[1])
                elif event[0] == "batch_done":
                    self._finish_batch(event[1])
                elif event[0] == "runtime_status":
                    self._apply_runtime_status(*event[1:])
                elif event[0] == "login_profile":
                    self._apply_login_profile(*event[1:])
        except Empty:
            pass
        self.root.after(150, self._drain_queue)

    def _finish_run(self, result) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.run_button.configure(text="立即生成并发布 →")
        self.batch_button.configure(state="normal")
        self.progress_var.set(f"{STATUS_TEXT.get(result.status, result.status.value)} · {result.message or '任务已结束'}")
        self._complete_progress(self.progress_var.get())
        self.refresh()
        if result.status == RunStatus.PUBLISHED:
            self._show_publish_success(result.url)
        elif result.status == RunStatus.NEEDS_REVIEW and result.article_path:
            if messagebox.askyesno("文章需要检查", f"{result.message}\n\n草稿已经保存，是否立即打开？"):
                os.startfile(result.article_path)
        elif result.status in {RunStatus.FAILED, RunStatus.UNKNOWN}:
            self._show_task_failure(
                result.message or STATUS_TEXT[result.status],
                uncertain=result.status == RunStatus.UNKNOWN,
            )
        elif result.status == RunStatus.SKIPPED and result.article_path:
            messagebox.showinfo("安全试运行完成", f"文章已保存：\n{result.article_path}")

    def _finish_batch(self, results: list[tuple[Account, PublishResult]]) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.run_button.configure(text="立即生成并发布 →")
        self.batch_button.configure(state="normal")
        self.retry_button.configure(state="normal")
        success = sum(result.status == RunStatus.PUBLISHED for _account, result in results)
        failed = sum(result.status in {RunStatus.FAILED, RunStatus.UNKNOWN, RunStatus.NEEDS_REVIEW} for _account, result in results)
        skipped = len(results) - success - failed
        self.progress_var.set(f"批量任务完成 · 成功 {success} · 失败/待处理 {failed} · 跳过 {skipped}")
        self._complete_progress(self.progress_var.get())
        self.refresh()
        self._show_batch_summary(results)

    def _show_batch_summary(self, results: list[tuple[Account, PublishResult]]) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("批量任务完成")
        dialog.configure(background=COLORS["surface"])
        dialog.transient(self.root)
        content = ttk.Frame(dialog, style="Surface.TFrame", padding=(28, 24))
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="批量任务已完成", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            content,
            text="每个账号独立记录结果；失败账号不会导致其他账号重复执行。",
            style="DialogText.TLabel",
        ).pack(anchor="w", pady=(5, 16))
        for account, result in results:
            row_panel = RoundedPanel(
                content,
                radius=10,
                padding=(14, 10),
                outer=COLORS["surface"],
            )
            row_panel.pack(fill="x", pady=(0, 8))
            row = row_panel.content
            color = COLORS["success"] if result.status == RunStatus.PUBLISHED else COLORS["danger"] if result.status in {RunStatus.FAILED, RunStatus.UNKNOWN} else COLORS["warning"]
            tk.Label(row, text="●", foreground=color, background=COLORS["surface"]).pack(side="left")
            ttk.Label(row, text=account.display_name, style="CardValue.TLabel").pack(side="left", padx=(8, 0))
            ttk.Label(row, text=STATUS_TEXT.get(result.status, result.status.value), style="CardDetail.TLabel").pack(side="right")
        RoundedButton(
            content,
            text="完成",
            variant="primary",
            command=dialog.destroy,
            outer=COLORS["surface"],
        ).pack(
            anchor="e", pady=(12, 0)
        )
        dialog.update_idletasks()
        width, height = 520, max(300, 205 + len(results) * 58)
        x = self.root.winfo_rootx() + max(10, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(10, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _show_publish_success(self, url: str | None) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("发布成功")
        dialog.configure(background=COLORS["surface"])
        dialog.resizable(False, False)
        dialog.transient(self.root)

        content = tk.Frame(dialog, background=COLORS["surface"], padx=30, pady=26)
        content.pack(fill="both", expand=True)
        tk.Label(
            content,
            text="✓",
            foreground=COLORS["success"],
            background=COLORS["primary_soft"],
            font=(FONT, 22, "bold"),
            width=3,
            height=1,
        ).pack(anchor="w")
        tk.Label(
            content,
            text="文章发布成功",
            foreground=COLORS["text"],
            background=COLORS["surface"],
            font=(FONT, 17, "bold"),
        ).pack(anchor="w", pady=(16, 6))
        tk.Label(
            content,
            text="51CTO 已确认提交完成，软件不会重复发布。",
            foreground=COLORS["muted"],
            background=COLORS["surface"],
            font=(FONT, 9),
        ).pack(anchor="w")

        actions = tk.Frame(content, background=COLORS["surface"])
        actions.pack(fill="x", pady=(24, 0))
        RoundedButton(
            actions,
            text="稍后",
            variant="secondary",
            command=dialog.destroy,
            outer=COLORS["surface"],
        ).pack(side="right")
        if url:
            def open_article() -> None:
                dialog.destroy()
                webbrowser.open(url)

            RoundedButton(
                actions,
                text="打开文章",
                variant="primary",
                command=open_article,
                outer=COLORS["surface"],
            ).pack(
                side="right", padx=(0, 10)
            )

        dialog.update_idletasks()
        width, height = 440, 270
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _show_task_failure(self, message: str, *, uncertain: bool = False) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("发布结果待确认" if uncertain else "任务已停止")
        dialog.configure(background=COLORS["surface"])
        dialog.resizable(False, False)
        dialog.transient(self.root)

        content = tk.Frame(dialog, background=COLORS["surface"], padx=30, pady=26)
        content.pack(fill="both", expand=True)
        tk.Label(
            content,
            text="?" if uncertain else "!",
            foreground=COLORS["warning"] if uncertain else COLORS["danger"],
            background=COLORS["primary_soft"] if uncertain else COLORS["danger_soft"],
            font=(FONT, 20, "bold"),
            width=3,
            height=1,
        ).pack(anchor="w")
        tk.Label(
            content,
            text="发布结果需要确认" if uncertain else "任务已安全停止",
            foreground=COLORS["text"],
            background=COLORS["surface"],
            font=(FONT, 17, "bold"),
        ).pack(anchor="w", pady=(16, 6))
        tk.Label(
            content,
            text=message,
            foreground=COLORS["muted"],
            background=COLORS["surface"],
            font=(FONT, 9),
            justify="left",
            wraplength=430,
        ).pack(anchor="w")
        tk.Label(
            content,
            text="安全保护已生效，软件不会重复提交。",
            foreground=COLORS["subtle"],
            background=COLORS["surface"],
            font=(FONT, 9),
        ).pack(anchor="w", pady=(8, 0))

        RoundedButton(
            content,
            text="知道了",
            variant="primary",
            command=dialog.destroy,
            outer=COLORS["surface"],
        ).pack(anchor="e", pady=(24, 0))

        dialog.update_idletasks()
        width, height = 500, 330
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def open_profile(self) -> None:
        url = self.current_account.profile_url or "https://blog.51cto.com/"
        webbrowser.open(url)
        self.progress_var.set("已使用默认浏览器打开 51CTO")

    def open_login(self) -> None:
        try:
            self.context.publisher_for_account(self.current_account_id).open_login()
            self._start_login_profile_sync()
            self.progress_var.set(f"已打开 {self.current_account.display_name} 的独立登录窗口")
            self._append_log(f"已打开 {self.current_account.display_name} 的 51CTO 登录窗口。")
        except Exception as exc:
            messagebox.showerror("无法打开自动发布登录窗口", str(exc))

    def _start_login_profile_sync(self) -> None:
        self.login_sync_generation += 1
        generation = self.login_sync_generation
        account_id = self.current_account_id
        publisher = self.context.publisher_for_account(account_id)
        self._append_log("正在等待 51CTO 登录完成并同步账号信息。")

        def worker() -> None:
            deadline = time.monotonic() + 120
            last_error = None
            while time.monotonic() < deadline:
                try:
                    snapshot = publisher.current_profile_snapshot()
                    self.queue.put(("login_profile", generation, account_id, snapshot, None))
                    return
                except Exception as exc:
                    last_error = str(exc)
                    time.sleep(3)
            self.queue.put(("login_profile", generation, account_id, None, last_error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_login_profile(
        self,
        generation: int,
        account_id: str,
        snapshot: ProfileSnapshot | None,
        error: str | None,
    ) -> None:
        if generation != self.login_sync_generation or account_id != self.current_account_id:
            return
        if snapshot is None:
            self._append_log(
                f"未能自动同步 51CTO 账号信息：{error or '登录后未识别到博客主页'}",
                "warning",
            )
            return

        account = self.context.account(account_id)
        detected_url = snapshot.profile_url.rstrip("/")
        configured_url = account.profile_url.rstrip("/")
        if configured_url and configured_url != detected_url:
            self._append_log(
                f"已登录账号与当前配置不一致，未覆盖。当前配置：{configured_url}；登录账号：{detected_url}",
                "warning",
            )
            self.progress_var.set("检测到登录账号与当前配置不一致，已停止自动覆盖")
            return

        display_name = account.display_name
        if snapshot.display_name and is_generic_account_name(display_name):
            display_name = snapshot.display_name
        updated = replace(account, profile_url=detected_url, display_name=display_name)
        try:
            saved = self.context.repository.save_account(updated)
        except ValueError:
            if display_name == account.display_name:
                self._append_log("账号信息同步失败：账号显示名称重复。", "error")
                return
            saved = self.context.repository.save_account(
                replace(account, profile_url=detected_url)
            )
            self._append_log(
                f"已同步 51CTO 主页：{detected_url}；昵称“{display_name}”已存在，暂未覆盖。",
                "warning",
            )
        except Exception as exc:
            self._append_log(f"账号信息同步失败：{exc}", "error")
            return
        else:
            name_note = f" · {saved.display_name}" if saved.display_name else ""
            self._append_log(f"已同步 51CTO 账号信息：{detected_url}{name_note}", "success")

        self.account_map[account_id] = saved
        self._show_account_name(saved)
        self.profile_snapshot = snapshot
        self.progress_var.set(f"已同步 51CTO 账号：{saved.display_name}")
        self.refresh()

    def install_schedule(self) -> None:
        try:
            accounts = self.context.accounts(enabled_only=True)
            self.context.scheduler.install([account.schedule_time for account in accounts])
            self._start_runtime_status_refresh(force=True)
            details = "、".join(f"{account.display_name} {account.schedule_time:%H:%M}" for account in accounts)
            messagebox.showinfo("定时任务", f"已更新多账号自动计划：\n{details}")
        except Exception as exc:
            messagebox.showerror("定时任务安装失败", str(exc))

    def open_latest_article(self) -> None:
        path = self.context.repository.latest_article_path(self.current_account_id)
        if path and Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showinfo("暂无文章", "还没有可打开的已保存文章。")

    def open_generated_dir(self) -> None:
        path = self.context.config_for_account(self.current_account_id).generated_dir
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)
