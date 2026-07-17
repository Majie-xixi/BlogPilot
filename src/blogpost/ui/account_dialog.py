from __future__ import annotations

from dataclasses import replace
from datetime import time
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from blogpost.application import ApplicationContext
from blogpost.domain import Account, DEFAULT_ACCOUNT_ID
from blogpost.publishers.cto51_profile import fetch_profile_snapshot
from blogpost.ui.theme import COLORS
from blogpost.ui.widgets import ModernCheckButton, RoundedButton, RoundedPanel


def is_generic_account_name(value: str) -> bool:
    return bool(re.fullmatch(r"账号\s*(?:\d+|[一二三四五])", value.strip()))


class AccountManagerDialog(tk.Toplevel):
    def __init__(self, master, context: ApplicationContext, on_saved) -> None:
        super().__init__(master)
        self.context = context
        self.on_saved = on_saved
        self.current_id = DEFAULT_ACCOUNT_ID
        self.name_lookup_results: queue.Queue[tuple[str, str, bool, str | None, str | None]] = (
            queue.Queue()
        )
        self.name_lookup_url: str | None = None
        self.name_lookup_var = tk.StringVar(value="同步名称")
        self.name_poll_id: str | None = None
        self.title("账号管理")
        self.configure(background=COLORS["surface"])
        self.transient(master)
        self.geometry(self._centered_geometry(900, 680))
        self.minsize(820, 630)
        self.vars = {
            "display_name": tk.StringVar(),
            "profile_url": tk.StringVar(),
            "schedule": tk.StringVar(value="10:00"),
            "monthly_target": tk.StringVar(value="21"),
            "category": tk.StringVar(value="AI 智能体"),
            "secondary_category": tk.StringVar(value="编程 Agent"),
            "personal_category": tk.StringVar(value="AI"),
            "article_type": tk.StringVar(value="技术解析"),
            "content_directions": tk.StringVar(),
            "keywords": tk.StringVar(),
            "article_subdir": tk.StringVar(value="default"),
            "enabled": tk.BooleanVar(value=True),
        }
        self._build()
        self._reload(DEFAULT_ACCOUNT_ID)
        self.name_poll_id = self.after(150, self._drain_name_lookup)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        self.focus_force()

    def _centered_geometry(self, width: int, height: int) -> str:
        self.update_idletasks()
        x = self.master.winfo_rootx() + max(10, (self.master.winfo_width() - width) // 2)
        y = self.master.winfo_rooty() + max(10, (self.master.winfo_height() - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _build(self) -> None:
        shell = ttk.Frame(self, style="Surface.TFrame", padding=(26, 22))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)
        ttk.Label(shell, text="账号管理", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            shell,
            text="账号信息、登录会话和文章目录均保存在本机；软件不会保存密码。",
            style="DialogText.TLabel",
        ).grid(row=0, column=1, sticky="e")

        sidebar_panel = RoundedPanel(
            shell,
            radius=12,
            padding=(12, 12),
            outer=COLORS["surface"],
        )
        sidebar_panel.grid(row=1, column=0, sticky="nsw", pady=(20, 0), padx=(0, 16))
        sidebar = sidebar_panel.content
        sidebar.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(sidebar, columns=("status",), show="tree headings", height=16)
        self.tree.heading("#0", text="账号")
        self.tree.heading("status", text="状态")
        self.tree.column("#0", width=150, minwidth=130)
        self.tree.column("status", width=62, minwidth=62, stretch=False, anchor="center")
        self.tree.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._select)
        RoundedButton(
            sidebar,
            text="新增账号",
            variant="primary",
            command=self._new,
            outer=COLORS["surface"],
        ).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

        form_panel = RoundedPanel(
            shell,
            radius=12,
            padding=(22, 15),
            outer=COLORS["surface"],
        )
        form_panel.grid(row=1, column=1, sticky="nsew", pady=(20, 0))
        form = form_panel.content
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        fields = (
            ("账号显示名称", "display_name", 0, 0),
            ("51CTO 博客主页", "profile_url", 0, 1),
            ("每日发布时间", "schedule", 2, 0),
            ("每月目标篇数", "monthly_target", 2, 1),
            ("文章大分类", "category", 4, 0),
            ("二级分类", "secondary_category", 4, 1),
            ("个人分类", "personal_category", 6, 0),
            ("文章保存子目录", "article_subdir", 6, 1),
            ("博文类型", "article_type", 8, 0),
            ("内容方向", "content_directions", 8, 1),
        )
        for label, name, row, column in fields:
            ttk.Label(form, text=label, style="Field.TLabel").grid(
                row=row, column=column, sticky="w", padx=(0 if column == 0 else 10, 10 if column == 0 else 0)
            )
            if name == "profile_url":
                control = ttk.Frame(form, style="Surface.TFrame")
                self.profile_entry = ttk.Entry(
                    control,
                    textvariable=self.vars[name],
                    style="Modern.TEntry",
                )
                self.profile_entry.pack(side="left", fill="x", expand=True)
                self.profile_entry.bind("<FocusOut>", self._auto_lookup_name)
                RoundedButton(
                    control,
                    textvariable=self.name_lookup_var,
                    variant="secondary",
                    command=lambda: self._start_name_lookup(force=True),
                    outer=COLORS["surface"],
                ).pack(side="left", padx=(8, 0))
            else:
                control = ttk.Entry(form, textvariable=self.vars[name], style="Modern.TEntry")
            control.grid(
                row=row + 1,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 10, 10 if column == 0 else 0),
                pady=(4, 7),
            )
        ttk.Label(form, text="主题关键词（作为文章主题硬约束）", style="Field.TLabel").grid(
            row=10, column=0, columnspan=2, sticky="w"
        )
        ttk.Entry(form, textvariable=self.vars["keywords"], style="Modern.TEntry").grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(4, 8)
        )
        ModernCheckButton(
            form,
            text="启用自动生成与发布",
            variable=self.vars["enabled"],
        ).grid(row=12, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            form,
            text="每个账号使用独立 Chrome 登录环境；登录失效只暂停该账号。",
            style="CardDetail.TLabel",
        ).grid(row=13, column=0, columnspan=2, sticky="w", pady=(6, 0))
        footer = ttk.Frame(shell, style="Surface.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        RoundedButton(
            footer,
            text="关闭",
            variant="secondary",
            command=self._close,
            outer=COLORS["surface"],
        ).grid(
            row=0, column=1
        )
        RoundedButton(
            footer,
            text="保存账号",
            variant="primary",
            command=self._save,
            outer=COLORS["surface"],
        ).grid(
            row=0, column=2, padx=(10, 0)
        )

    def _reload(self, selected_id: str | None = None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        accounts = self.context.accounts()
        for account in accounts:
            self.tree.insert(
                "",
                "end",
                iid=account.id,
                text=account.display_name,
                values=("启用" if account.enabled else "停用",),
            )
        wanted = selected_id if selected_id in {a.id for a in accounts} else accounts[0].id
        self.tree.selection_set(wanted)
        self.tree.focus(wanted)
        self._load_account(self.context.account(wanted))

    def _select(self, _event=None) -> None:
        selected = self.tree.selection()
        if selected:
            self._load_account(self.context.account(selected[0]))

    def _load_account(self, account: Account) -> None:
        self.current_id = account.id
        values = {
            "display_name": account.display_name,
            "profile_url": account.profile_url,
            "schedule": account.schedule_time.strftime("%H:%M"),
            "monthly_target": str(account.monthly_target),
            "category": account.category,
            "secondary_category": account.secondary_category,
            "personal_category": account.personal_category,
            "article_type": account.article_type,
            "content_directions": account.content_directions,
            "keywords": account.keywords,
            "article_subdir": account.article_subdir,
            "enabled": account.enabled,
        }
        for name, value in values.items():
            self.vars[name].set(value)
        self.name_lookup_var.set("同步名称")
        if account.profile_url and is_generic_account_name(account.display_name):
            self.after_idle(self._start_name_lookup)

    def _new(self) -> None:
        if len(self.context.accounts()) >= 5:
            messagebox.showinfo("账号数量已满", "最多可以配置 5 个账号。", parent=self)
            return
        token = uuid.uuid4().hex[:8]
        self.current_id = f"account-{token}"
        self.vars["display_name"].set(f"账号 {len(self.context.accounts()) + 1}")
        self.vars["profile_url"].set("")
        self.vars["schedule"].set("10:20")
        self.vars["monthly_target"].set("21")
        self.vars["category"].set("AI 智能体")
        self.vars["secondary_category"].set("编程 Agent")
        self.vars["personal_category"].set("AI")
        self.vars["article_type"].set("技术解析")
        self.vars["content_directions"].set("AI Agent、AI 编程、Prompt、AIOps、边缘 AI、大模型工程")
        self.vars["keywords"].set("")
        self.vars["article_subdir"].set(self.current_id)
        self.vars["enabled"].set(True)
        self.name_lookup_var.set("同步名称")
        self.tree.selection_remove(self.tree.selection())

    def _auto_lookup_name(self, _event=None) -> None:
        if not self.vars["profile_url"].get().strip():
            return
        if not self.vars["display_name"].get().strip() or is_generic_account_name(
            self.vars["display_name"].get()
        ):
            self._start_name_lookup()

    def _start_name_lookup(self, *, force: bool = False) -> None:
        url = self.vars["profile_url"].get().strip().rstrip("/")
        if not re.fullmatch(r"https://blog\.51cto\.com/u_\d+", url):
            if force:
                self.name_lookup_var.set("主页格式错误")
            return
        if self.name_lookup_url == url:
            return
        current_name = self.vars["display_name"].get().strip()
        if not force and current_name and not is_generic_account_name(current_name):
            return
        account_id = self.current_id
        self.name_lookup_url = url
        self.name_lookup_var.set("读取中…")
        threading.Thread(
            target=self._name_lookup_worker,
            args=(account_id, url, force),
            daemon=True,
        ).start()

    def _name_lookup_worker(self, account_id: str, url: str, force: bool) -> None:
        try:
            display_name = fetch_profile_snapshot(url).display_name
            error = None if display_name else "主页未提供可识别的博主名称"
        except Exception as exc:
            display_name = None
            error = str(exc)
        self.name_lookup_results.put((account_id, url, force, display_name, error))

    def _drain_name_lookup(self) -> None:
        try:
            while True:
                account_id, url, force, display_name, error = self.name_lookup_results.get_nowait()
                if self.name_lookup_url == url:
                    self.name_lookup_url = None
                if account_id != self.current_id:
                    continue
                if self.vars["profile_url"].get().strip().rstrip("/") != url:
                    continue
                if error or not display_name:
                    self.name_lookup_var.set("读取失败")
                    continue
                current_name = self.vars["display_name"].get().strip()
                if force or not current_name or is_generic_account_name(current_name):
                    self.vars["display_name"].set(display_name)
                    self.name_lookup_var.set("已同步")
                    self._save_synced_name(account_id, url, display_name)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.name_poll_id = self.after(150, self._drain_name_lookup)

    def _save_synced_name(self, account_id: str, url: str, display_name: str) -> None:
        existing = {account.id: account for account in self.context.accounts()}
        account = existing.get(account_id)
        if account is None or account.profile_url.rstrip("/") != url:
            return
        if account.display_name == display_name:
            return
        self.context.repository.save_account(replace(account, display_name=display_name))
        if self.tree.exists(account_id):
            self.tree.item(account_id, text=display_name)
        self.on_saved(account_id)

    def _close(self) -> None:
        if self.name_poll_id is not None:
            try:
                self.after_cancel(self.name_poll_id)
            except tk.TclError:
                pass
            self.name_poll_id = None
        self.destroy()

    def _save(self) -> None:
        try:
            hour_text, minute_text = self.vars["schedule"].get().strip().split(":", 1)
            existing = {account.id: account for account in self.context.accounts()}
            sort_order = existing.get(self.current_id).sort_order if self.current_id in existing else len(existing)
            account = Account(
                id=self.current_id,
                display_name=self.vars["display_name"].get().strip(),
                profile_url=self.vars["profile_url"].get().strip().rstrip("/"),
                enabled=self.vars["enabled"].get(),
                sort_order=sort_order,
                schedule_time=time(int(hour_text), int(minute_text)),
                monthly_target=int(self.vars["monthly_target"].get().strip()),
                category=self.vars["category"].get().strip(),
                secondary_category=self.vars["secondary_category"].get().strip(),
                personal_category=self.vars["personal_category"].get().strip(),
                article_type=self.vars["article_type"].get().strip(),
                content_directions=self.vars["content_directions"].get().strip(),
                keywords=self.vars["keywords"].get().strip(),
                article_subdir=self.vars["article_subdir"].get().strip(),
            )
            self.context.repository.save_account(account)
            self._reload(account.id)
            self.on_saved(account.id)
        except Exception as exc:
            messagebox.showerror("账号设置无效", str(exc), parent=self)


class BatchPublishDialog(tk.Toplevel):
    def __init__(self, master, accounts: list[Account], on_confirm) -> None:
        super().__init__(master)
        self.title("选择发布账号")
        self.configure(background=COLORS["surface"])
        self.transient(master)
        self.resizable(False, False)
        self.on_confirm = on_confirm
        self.vars = {account.id: tk.BooleanVar(value=True) for account in accounts}
        content = ttk.Frame(self, style="Surface.TFrame", padding=(28, 24))
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="依次生成并发布", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            content,
            text="所选账号将按顺序串行处理；某个账号失败后仍会继续下一个。",
            style="DialogText.TLabel",
        ).pack(anchor="w", pady=(5, 16))
        for account in accounts:
            row_panel = RoundedPanel(
                content,
                radius=10,
                padding=(14, 10),
                outer=COLORS["surface"],
            )
            row_panel.pack(fill="x", pady=(0, 8))
            row = row_panel.content
            ModernCheckButton(
                row,
                text=account.display_name,
                variable=self.vars[account.id],
            ).pack(side="left", fill="x", expand=True)
            ttk.Label(
                row,
                text=f"{account.schedule_time:%H:%M} · 目标 {account.monthly_target} 篇",
                style="CardDetail.TLabel",
            ).pack(side="right")
        actions = ttk.Frame(content, style="Surface.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        RoundedButton(
            actions,
            text="取消",
            variant="secondary",
            command=self.destroy,
            outer=COLORS["surface"],
        ).pack(side="right")
        RoundedButton(
            actions,
            text="开始执行",
            variant="primary",
            command=self._confirm,
            outer=COLORS["surface"],
        ).pack(
            side="right", padx=(0, 10)
        )
        self.update_idletasks()
        width, height = 500, max(270, 190 + len(accounts) * 54)
        x = master.winfo_rootx() + max(10, (master.winfo_width() - width) // 2)
        y = master.winfo_rooty() + max(10, (master.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.grab_set()
        self.focus_force()

    def _confirm(self) -> None:
        selected = [account_id for account_id, variable in self.vars.items() if variable.get()]
        if not selected:
            messagebox.showinfo("请选择账号", "至少选择一个账号。", parent=self)
            return
        self.destroy()
        self.on_confirm(selected)
