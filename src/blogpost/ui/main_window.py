from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from blogpost.application import ApplicationContext
from blogpost.domain import Article, PublishResult, RunStatus, Trigger
from blogpost.markdown import parse_markdown
from blogpost.paths import app_data_dir, log_path
from blogpost.run_lock import AlreadyRunning, RunLock
from blogpost.ui.settings_dialog import SettingsDialog
from blogpost.ui.theme import COLORS, FONT


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


class MainWindow:
    def __init__(self, root: tk.Tk, context: ApplicationContext):
        self.root = root
        self.context = context
        self.queue: Queue[tuple] = Queue()
        self.running = False
        self._build()
        self.refresh()
        self._load_recent_log()
        self.root.after(150, self._drain_queue)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        page = ttk.Frame(self.root, style="Page.TFrame", padding=(30, 24, 30, 20))
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
        ttk.Button(header, text="设置", style="Secondary.TButton", command=self.open_settings).grid(
            row=0, column=1, rowspan=2, sticky="e"
        )

        stats = ttk.Frame(page, style="Page.TFrame")
        stats.grid(row=1, column=0, sticky="ew", pady=(22, 14))
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

        hero = ttk.Frame(page, style="Hero.TFrame", padding=(24, 17))
        hero.grid(row=2, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, text="准备生成今天的 AI 技术博文", style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.progress_var = tk.StringVar(value="准备就绪 · 点击右侧按钮即可开始")
        ttk.Label(hero, textvariable=self.progress_var, style="HeroText.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.run_button = ttk.Button(
            hero,
            text="立即生成并发布",
            style="HeroButton.TButton",
            command=self.run_now,
        )
        self.run_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(24, 0))
        self.progressbar = ttk.Progressbar(
            hero,
            mode="determinate",
            value=0,
            style="App.Horizontal.TProgressbar",
        )
        self.progressbar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(13, 0))

        actions = ttk.Frame(page, style="Page.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(14, 18))
        for text, command in (
            ("打开 51CTO 登录窗口", self.open_login),
            ("安装 / 更新每日任务", self.install_schedule),
            ("打开最近文章", self.open_latest_article),
            ("打开文章目录", self.open_generated_dir),
        ):
            button = ttk.Button(actions, text=text, style="Secondary.TButton", command=command)
            button.pack(side="left", padx=(0 if not actions.winfo_children() else 10, 0))
            if text == "打开最近文章":
                self.latest_article_button = button

        self.retry_button = ttk.Button(
            actions,
            text="重新发布最近文章",
            style="Secondary.TButton",
            command=self.retry_latest_article,
        )
        self.retry_button.pack(side="left", padx=(10, 0))

        section = ttk.Frame(page, style="Page.TFrame")
        section.grid(row=4, column=0, sticky="ew", pady=(0, 7))
        section.columnconfigure(0, weight=1)
        self.detail_title_var = tk.StringVar(value="运行日志")
        self.detail_hint_var = tk.StringVar(value="生成、检查、保存和发布步骤会实时显示")
        ttk.Label(section, textvariable=self.detail_title_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(section, textvariable=self.detail_hint_var, style="Subtitle.TLabel").grid(
            row=0, column=1, sticky="e", padx=(0, 12)
        )
        self.detail_toggle_button = ttk.Button(
            section, text="查看历史记录", style="Link.TButton", command=self._toggle_detail_view
        )
        self.detail_toggle_button.grid(row=0, column=2, sticky="e")

        detail_stack = ttk.Frame(page, style="Page.TFrame")
        detail_stack.grid(row=5, column=0, sticky="nsew")
        detail_stack.columnconfigure(0, weight=1)
        detail_stack.rowconfigure(0, weight=1)
        self.log_view = ttk.Frame(detail_stack, style="Card.TFrame", padding=1)
        self.history_view = ttk.Frame(detail_stack, style="Card.TFrame", padding=1)
        self.log_view.grid(row=0, column=0, sticky="nsew")
        self.history_view.grid(row=0, column=0, sticky="nsew")
        self.log_view.tkraise()
        self.detail_view = "log"

        self.log_view.columnconfigure(0, weight=1)
        self.log_view.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            self.log_view,
            wrap="word",
            state="disabled",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            selectbackground=COLORS["primary_soft"],
            relief="flat",
            borderwidth=0,
            font=(FONT, 9),
            padx=14,
            pady=12,
        )
        log_scrollbar = ttk.Scrollbar(self.log_view, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.tag_configure("success", foreground=COLORS["success"])
        self.log_text.tag_configure("warning", foreground=COLORS["warning"])
        self.log_text.tag_configure("error", foreground=COLORS["danger"])
        self.log_text.tag_configure("muted", foreground=COLORS["muted"])

        self.history_view.columnconfigure(0, weight=1)
        self.history_view.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            self.history_view,
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
        self.history_scrollbar = ttk.Scrollbar(self.history_view, orient="vertical", command=self.tree.yview)
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
        card = ttk.Frame(parent, style="Card.TFrame", padding=(18, 15))
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        card.columnconfigure(1, weight=1)
        tk.Label(card, text="●", foreground=dot_color, background=COLORS["surface"], font=(FONT, 8)).grid(
            row=0, column=0, sticky="w", padx=(0, 7)
        )
        ttk.Label(card, text=caption, style="CardCaption.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(card, textvariable=value_var, style="CardValue.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 3)
        )
        ttk.Label(card, textvariable=detail_var, style="CardDetail.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

    def refresh(self) -> None:
        cfg = self.context.config
        self.schedule_value_var.set(f"每天 {cfg.schedule_time:%H:%M}")
        today = date.today()
        published = self.context.repository.has_successful_publication(today)
        tracked_days = self.context.repository.count_successful_days(today.year, today.month)
        self.today_value_var.set("已发布" if published else "尚未发布")
        self.today_detail_var.set(f"软件记录：本月已发布 {tracked_days} 天")
        if cfg.dry_run:
            self.mode_value_var.set("安全试运行")
            self.mode_detail_var.set("填写编辑器，不点击最终发布")
        else:
            self.mode_value_var.set("真实发布")
            self.mode_detail_var.set("检查通过后自动提交到 51CTO")

        for item in self.tree.get_children():
            self.tree.delete(item)
        runs = list(self.context.repository.recent_runs(30))
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
                    "手动" if run.trigger == Trigger.MANUAL else "定时",
                    STATUS_TEXT.get(run.status, run.status.value),
                    run.error_summary or "—",
                ),
                tags=(tag,) if tag else (),
            )
        latest = self.context.repository.latest_article_path()
        self.latest_article_button.configure(state="normal" if latest and Path(latest).exists() else "disabled")
        self.retry_button.configure(
            state="normal" if latest and Path(latest).exists() and not self.running else "disabled"
        )

    def _load_recent_log(self) -> None:
        path = log_path()
        if not path.exists() or not path.stat().st_size:
            self._append_log("等待任务开始。生成、检查、保存和发布步骤会显示在这里。", "muted", timestamp=False)
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            self.log_text.configure(state="normal")
            self.log_text.insert("end", "\n".join(lines) + "\n", "muted")
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        except OSError:
            self._append_log("无法读取历史日志，但不影响运行。", "warning", timestamp=False)

    def _append_log(self, message: str, tag: str | None = None, *, timestamp: bool = True) -> None:
        prefix = f"[{datetime.now():%H:%M:%S}] " if timestamp else ""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", prefix + message.rstrip() + "\n", tag or "")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _show_log_view(self) -> None:
        self.detail_view = "log"
        self.log_view.tkraise()
        self.detail_title_var.set("运行日志")
        self.detail_hint_var.set("生成、检查、保存和发布步骤会实时显示")
        self.detail_toggle_button.configure(text="查看历史记录")

    def _toggle_detail_view(self) -> None:
        if self.detail_view == "log":
            self.detail_view = "history"
            self.history_view.tkraise()
            self.detail_title_var.set("历史记录")
            self.detail_hint_var.set("最多显示最近 30 次运行结果")
            self.detail_toggle_button.configure(text="返回运行日志")
        else:
            self._show_log_view()

    def open_settings(self) -> None:
        SettingsDialog(self.root, self.context, self.refresh)

    def run_now(self) -> None:
        if self.running:
            return
        allow = False
        if self.context.repository.has_successful_publication(date.today()):
            allow = messagebox.askyesno("今天已经发布", "今天已有成功发布记录，仍要再生成并发布一篇吗？")
            if not allow:
                return
        try:
            pipeline = self.context.build_pipeline()
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        self.running = True
        self._clear_log()
        self._append_log("任务已启动，正在准备历史语料和选题。")
        self._show_log_view()
        self.progress_var.set("任务已启动 · 正在准备选题")
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(12)
        self.run_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        threading.Thread(target=self._run_worker, args=(pipeline, allow), daemon=True).start()

    def retry_latest_article(self) -> None:
        if self.running:
            return
        path_text = self.context.repository.latest_article_path()
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
        self.progress_var.set("正在重新发布 · 不会重新生成文章")
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(12)
        self.run_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        threading.Thread(target=self._retry_worker, args=(path,), daemon=True).start()

    def _retry_worker(self, path: Path) -> None:
        run = None
        try:
            with RunLock(app_data_dir() / "run.lock"):
                markdown = path.read_text(encoding="utf-8")
                document = parse_markdown(markdown)
                article = Article(document.title, markdown, document.title)
                run = self.context.repository.create_publish_retry(str(path))
                self.queue.put(("progress", RunStatus.PUBLISHING, "正在重新填写 51CTO 编辑器，不调用大模型"))
                result = self.context.publisher.publish(
                    article,
                    self.context.config.category,
                    self.context.config.dry_run,
                )
                if result.status in {RunStatus.PUBLISHED, RunStatus.UNKNOWN, RunStatus.FAILED}:
                    self.context.repository.update_run(
                        run.id,
                        result.status,
                        error_code=None if result.status == RunStatus.PUBLISHED else "publish_failed",
                        error_summary=result.message,
                    )
                else:
                    self.context.repository.force_run_status(run.id, result.status)
                result = PublishResult(
                    result.status,
                    url=result.url,
                    message=result.message,
                    article_path=str(path),
                )
        except AlreadyRunning as exc:
            result = PublishResult(RunStatus.SKIPPED, message=str(exc), article_path=str(path))
        except Exception as exc:
            if run is not None:
                self.context.repository.force_run_status(run.id, RunStatus.FAILED)
            result = PublishResult(RunStatus.FAILED, message=str(exc), article_path=str(path))
        self.queue.put(("done", result))

    def _run_worker(self, pipeline, allow: bool) -> None:
        result = pipeline.run(
            Trigger.MANUAL,
            allow_same_day=allow,
            progress=lambda status, message: self.queue.put(("progress", status, message)),
        )
        self.queue.put(("done", result))

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self.queue.get_nowait()
                if event[0] == "progress":
                    _, status, message = event
                    self.progress_var.set(f"{STATUS_TEXT.get(status, status.value)} · {message}")
                    tag = "error" if status == RunStatus.FAILED else "warning" if status in {RunStatus.NEEDS_REVIEW, RunStatus.UNKNOWN} else "success" if status == RunStatus.PUBLISHED else None
                    self._append_log(f"{STATUS_TEXT.get(status, status.value)}：{message}", tag)
                elif event[0] == "done":
                    self._finish_run(event[1])
        except Empty:
            pass
        self.root.after(150, self._drain_queue)

    def _finish_run(self, result) -> None:
        self.running = False
        self.progressbar.stop()
        self.progressbar.configure(mode="determinate", value=100)
        self.run_button.configure(state="normal")
        self.progress_var.set(f"{STATUS_TEXT.get(result.status, result.status.value)} · {result.message or '任务已结束'}")
        self.refresh()
        if result.status == RunStatus.PUBLISHED and result.url:
            if messagebox.askyesno("发布成功", "文章已发布，是否立即打开？"):
                webbrowser.open(result.url)
        elif result.status == RunStatus.NEEDS_REVIEW and result.article_path:
            if messagebox.askyesno("文章需要检查", f"{result.message}\n\n草稿已经保存，是否立即打开？"):
                os.startfile(result.article_path)
        elif result.status in {RunStatus.FAILED, RunStatus.UNKNOWN}:
            messagebox.showwarning("任务已停止", result.message or STATUS_TEXT[result.status])
        elif result.status == RunStatus.SKIPPED and result.article_path:
            messagebox.showinfo("安全试运行完成", f"文章已保存：\n{result.article_path}")

    def open_login(self) -> None:
        try:
            self.context.publisher.open_login()
            self.progress_var.set("已打开独立 Chrome 登录窗口 · 请完成 51CTO 登录")
            self._append_log("已打开 51CTO 登录窗口。")
        except Exception as exc:
            messagebox.showerror("无法打开登录窗口", str(exc))

    def install_schedule(self) -> None:
        try:
            self.context.scheduler.install(self.context.config.schedule_time)
            messagebox.showinfo("定时任务", f"已设置每天 {self.context.config.schedule_time:%H:%M} 自动执行")
        except Exception as exc:
            messagebox.showerror("定时任务安装失败", str(exc))

    def open_latest_article(self) -> None:
        path = self.context.repository.latest_article_path()
        if path and Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showinfo("暂无文章", "还没有可打开的已保存文章。")

    def open_generated_dir(self) -> None:
        path = self.context.config.generated_dir
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)
