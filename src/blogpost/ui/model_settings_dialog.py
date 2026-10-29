from __future__ import annotations

from dataclasses import replace
import json
import queue
import shutil
import threading
import os
import tkinter as tk
from tkinter import messagebox, ttk
from uuid import uuid4

from blogpost.config import ModelConnection
from blogpost.llm.client import OpenAICompatibleClient
from blogpost.paths import config_path
from blogpost.ui.settings_state import SettingsState
from blogpost.ui.theme import COLORS, FONT
from blogpost.ui.widgets import RoundedButton


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, context, on_saved):
        super().__init__(master)
        self.withdraw()
        self.context, self.on_saved = context, on_saved
        self.state = SettingsState(context.config)
        self.selected_id = self.state.active_id
        self.page = 'model'
        self.values = {key: tk.StringVar(self) for key in ('name', 'vendor', 'base_url', 'model', 'key')}
        self.show_key = tk.BooleanVar(self, value=False)
        self.dry_run = tk.BooleanVar(self, value=self.state.dry_run)
        self.status = tk.StringVar(self)
        for value in self.values.values():
            value.trace_add('write', lambda *_: self.status.set(''))
        self.title('设置')
        self.configure(background=COLORS['surface'])
        self.transient(master)
        self.resizable(True, True)
        self._build()
        self._refresh_list()
        self._show_connection()
        self.update_idletasks()
        self._place_in_work_area()
        self.deiconify()
        self.lift()
        self.grab_set()

    def _build(self):
        shell = ttk.Frame(self, style='Surface.TFrame')
        shell.pack(fill='both', expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)
        side = tk.Frame(shell, background=COLORS['surface_alt'], padx=16, pady=18, width=230)
        side.grid(row=0, column=0, sticky='ns')
        side.pack_propagate(False)
        tk.Label(side, text='设置', background=COLORS['surface_alt'], foreground=COLORS['muted'], font=(FONT, 11)).pack(anchor='w', pady=(0, 12))
        self.model_nav = RoundedButton(side, text='模型服务', variant='toggle', selected=True, anchor='w', outer=COLORS['surface_alt'], command=lambda: self._show_page('model'))
        self.model_nav.pack(fill='x', pady=2)
        self.safety_nav = RoundedButton(side, text='发布安全', variant='toggle', anchor='w', outer=COLORS['surface_alt'], command=lambda: self._show_page('safety'))
        self.safety_nav.pack(fill='x', pady=2)
        ttk.Separator(side).pack(fill='x', pady=12)
        tk.Label(side, text='已保存的连接', background=COLORS['surface_alt'], foreground=COLORS['muted'], font=(FONT, 9)).pack(anchor='w', pady=(0, 6))
        list_area = tk.Frame(side, background=COLORS['surface_alt'])
        list_area.pack(fill='both', expand=True)
        self.list_canvas = tk.Canvas(list_area, background=COLORS['surface_alt'], highlightthickness=0, width=185)
        self.list_canvas.pack(side='left', fill='both', expand=True)
        list_scroll = ttk.Scrollbar(list_area, orient='vertical', command=self.list_canvas.yview)
        list_scroll.pack(side='right', fill='y')
        def list_scroll_state(first, last):
            list_scroll.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                list_scroll.pack_forget()
            elif not list_scroll.winfo_manager():
                list_scroll.pack(side='right', fill='y')
        self.list_canvas.configure(yscrollcommand=list_scroll_state)
        self.connection_list = tk.Frame(self.list_canvas, background=COLORS['surface_alt'])
        self.list_window = self.list_canvas.create_window(0, 0, anchor='nw', window=self.connection_list)
        self.connection_list.bind('<Configure>', lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox('all')))
        self.list_canvas.bind('<Configure>', lambda e: self.list_canvas.itemconfigure(self.list_window, width=e.width))
        RoundedButton(side, text='+ 添加连接', outer=COLORS['surface_alt'], command=self._add).pack(fill='x', pady=(8, 2))

        body = ttk.Frame(shell, style='Surface.TFrame')
        body.grid(row=0, column=1, sticky='nsew')
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, background=COLORS['surface'], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scroll = ttk.Scrollbar(body, orient='vertical', command=self.canvas.yview)
        self.scroll.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.content = ttk.Frame(self.canvas, style='Surface.TFrame', padding=(24, 20, 24, 12))
        self.content.columnconfigure(0, minsize=125)
        self.content.columnconfigure(1, weight=1)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self._content_resized)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind('<MouseWheel>', self._wheel)
        footer = ttk.Frame(shell, style='Surface.TFrame', padding=(16, 12))
        footer.grid(row=1, column=0, columnspan=2, sticky='ew')
        RoundedButton(footer, text='保存设置', variant='primary', command=self._save).pack(side='right')
        RoundedButton(footer, text='取消', command=self.destroy).pack(side='right', padx=(0, 10))

    def _wheel(self, event):
        for canvas in (self.list_canvas, self.canvas):
            x, y = canvas.winfo_rootx(), canvas.winfo_rooty()
            if x <= event.x_root < x + canvas.winfo_width() and y <= event.y_root < y + canvas.winfo_height():
                canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
                return 'break'

    def _content_resized(self, event):
        for child in self.content.winfo_children():
            if isinstance(child, ttk.Label) and int(child.cget('wraplength') or 0) > 0:
                column = int(child.grid_info().get('column', 0))
                width = max(80, event.width - (175 if column == 1 else 50))
                if int(child.cget('wraplength')) != width:
                    child.configure(wraplength=width)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _connection(self):
        return next(c for c in self.state.connections if c.id == self.selected_id)

    def _refresh_list(self):
        for child in self.connection_list.winfo_children():
            child.destroy()
        for c in self.state.connections:
            subtitle = '本地客户端' if c.kind == 'codex' else 'API'
            if c.id == self.state.active_id:
                subtitle += ' · 当前使用'
            selected = c.id == self.selected_id and self.page == 'model'
            RoundedButton(self.connection_list, text=f'{c.name}\n{subtitle}', height=62,
                          font=(FONT, 10), variant='toggle' if selected else 'identity', anchor='w',
                          selected=selected,
                          outer=COLORS['surface_alt'], command=lambda item=c.id: self._select(item)).pack(fill='x', pady=(0, 3))

    def _capture(self):
        if self.page != 'model':
            return
        c = self._connection()
        c.name = self.values['name'].get().strip()
        if c.kind == 'api':
            c.vendor = self.values['vendor'].get()
            c.base_url = self.values['base_url'].get().strip()
            c.model = self.values['model'].get().strip()
            key = self.values['key'].get().strip()
            if key:
                self.state.keys[c.id] = key

    def _select(self, target):
        if target == self.selected_id and self.page == 'model':
            return
        self._capture()
        self.selected_id = target
        self.page = 'model'
        self.model_nav.configure(selected=True)
        self.safety_nav.configure(selected=False)
        self._refresh_list()
        self._show_connection()

    def _add(self):
        self._capture()
        c = ModelConnection(uuid4().hex, '新连接', 'api', '自定义', '', '')
        self.state.connections.append(c)
        self.selected_id, self.page = c.id, 'model'
        self.model_nav.configure(selected=True)
        self.safety_nav.configure(selected=False)
        self._refresh_list()
        self._show_connection()

    def _delete(self):
        c = self._connection()
        if c.kind != 'api':
            return
        if c.id == self.state.active_id:
            messagebox.showinfo('无法删除', '请先将其他连接设为当前连接。', parent=self)
            return
        if not messagebox.askyesno('删除连接', f'删除连接“{c.name}”？保存设置后生效。已保存的密钥将删除，保留加密备份；环境变量不会改变。', parent=self):
            return
        self.state.remove_connection(c.id)
        self.selected_id = self.state.active_id
        self._refresh_list()
        self._show_connection()

    def _clear(self):
        if hasattr(self, '_safety_trace'):
            self.dry_run.trace_remove('write', self._safety_trace)
            del self._safety_trace
        for child in self.content.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)

    def _show_page(self, page):
        self._capture()
        self.page = page
        self.model_nav.configure(selected=page == 'model')
        self.safety_nav.configure(selected=page == 'safety')
        self._refresh_list()
        if page == 'model':
            self._show_connection()
        else:
            self._clear()
            ttk.Label(self.content, text='全局发布安全', style='DialogTitle.TLabel', font=(FONT, 17, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
            ttk.Label(self.content, text='此设置适用于所有账号和模型连接。', style='DialogText.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 20))
            self.safety_label = tk.StringVar(self)
            safety_button = RoundedButton(self.content, textvariable=self.safety_label, variant='toggle',
                                          command=lambda: self.dry_run.set(not self.dry_run.get()))
            def update_safety(*_):
                self.safety_label.set('安全试运行：已开启' if self.dry_run.get() else '安全试运行：已关闭')
                safety_button.configure(selected=self.dry_run.get())
            update_safety()
            safety_button.grid(row=2, column=0, columnspan=2, sticky='w')
            self._safety_trace = self.dry_run.trace_add('write', update_safety)
            ttk.Label(self.content, text='点击切换状态。开启后填写编辑器，但不点击最终发布。', style='DialogText.TLabel', wraplength=440).grid(row=3, column=0, columnspan=2, sticky='w', pady=(8, 0))
            ttk.Label(self.content, text='发布时间、主页、文章分类和内容方向由每个账号独立配置。', style='DialogText.TLabel', wraplength=440).grid(row=4, column=0, columnspan=2, sticky='w', pady=(16, 0))

    def _field(self, row, label, name):
        ttk.Label(self.content, text=label, style='Field.TLabel', font=(FONT, 10, 'bold')).grid(row=row, column=0, sticky='nw', padx=(0, 20), pady=(18, 0))
        if name == 'key':
            holder = ttk.Frame(self.content, style='Surface.TFrame')
            holder.grid(row=row, column=1, sticky='ew', pady=(10, 0))
            holder.columnconfigure(0, weight=1)
            entry = ttk.Entry(holder, textvariable=self.values[name], style='Modern.TEntry', show='•')
            entry.grid(row=0, column=0, sticky='ew')
            def toggle():
                self.show_key.set(not self.show_key.get())
                entry.configure(show='' if self.show_key.get() else '•')
                toggle_button.configure(text='隐藏' if self.show_key.get() else '显示')
            toggle_button = RoundedButton(holder, text='显示', command=toggle)
            toggle_button.grid(row=0, column=1, padx=(8, 0))
            self.show_key.set(False)
        else:
            entry = ttk.Entry(self.content, textvariable=self.values[name], style='Modern.TEntry')
            entry.grid(row=row, column=1, sticky='ew', pady=(10, 0))
        return entry

    def _show_connection(self):
        self._clear()
        c = self._connection()
        for name in ('name', 'vendor', 'base_url', 'model'):
            self.values[name].set(getattr(c, name))
        self.values['key'].set(self.state.keys.get(c.id, ''))
        title = ttk.Frame(self.content, style='Surface.TFrame')
        title.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))
        ttk.Label(title, text=c.name, style='DialogTitle.TLabel', font=(FONT, 17, 'bold')).pack(side='left')
        if c.id == self.state.active_id:
            tk.Label(title, text='当前使用', background=COLORS['primary_soft'], foreground=COLORS['primary'], font=(FONT, 9), padx=10, pady=3).pack(side='left', padx=(12, 0))
        self._field(1, '连接名称', 'name')
        ttk.Label(self.content, text='用于在本地识别此连接。', style='CardDetail.TLabel').grid(row=2, column=1, sticky='w', pady=(3, 0))
        ttk.Label(self.content, text='接入方式', style='Field.TLabel').grid(row=3, column=0, sticky='nw', pady=(18, 0))
        ttk.Label(self.content, text='本地客户端' if c.kind == 'codex' else 'API（OpenAI 兼容）', style='DialogText.TLabel').grid(row=3, column=1, sticky='w', pady=(18, 0))
        if c.kind == 'codex':
            ttk.Label(self.content, text='使用本机 Codex CLI 的登录与模型配置。请先安装并登录 Codex；定时任务也需要在相同运行环境中可用。', style='DialogText.TLabel', wraplength=440).grid(row=4, column=1, sticky='w', pady=(12, 0))
            ttk.Label(self.content, text='客户端：' + ('已找到' if shutil.which('codex') else '未找到'), style='CardDetail.TLabel').grid(row=5, column=1, sticky='w', pady=(10, 0))
        else:
            ttk.Label(self.content, text='供应商', style='Field.TLabel').grid(row=4, column=0, sticky='nw', pady=(18, 0))
            style = ttk.Style(self)
            style.configure('Settings.TCombobox', padding=(10, 7), fieldbackground=COLORS['surface'])
            style.map('Settings.TCombobox', fieldbackground=[('readonly', COLORS['surface'])])
            vendor = ttk.Combobox(self.content, textvariable=self.values['vendor'], values=('DeepSeek', 'OpenAI', '自定义'), state='readonly', style='Settings.TCombobox')
            vendor.grid(row=4, column=1, sticky='ew', pady=(12, 0))
            vendor.bind('<<ComboboxSelected>>', self._vendor_selected)
            self._field(6, 'API 地址', 'base_url')
            ttk.Label(self.content, text='填写 OpenAI 兼容接口的 Base URL。', style='CardDetail.TLabel').grid(row=7, column=1, sticky='w', pady=(3, 0))
            self._field(8, '模型名称', 'model')
            self._field(10, 'API Key', 'key')
            try:
                has_key = bool(self.context.secrets.get_api_key(c.id))
                hint = '已保存密钥，输入新密钥可更换' if has_key else '尚未保存密钥'
            except Exception:
                hint = '无法读取已保存的密钥，请检查本机用户权限'
            if c.id == 'legacy-api':
                if os.environ.get('BLOGPOST_API_KEY'):
                    hint = '当前使用 BLOGPOST_API_KEY 环境变量；保存的密钥在其移除后生效'
            ttk.Label(self.content, text=hint, style='CardDetail.TLabel', wraplength=440).grid(row=12, column=1, sticky='w', pady=(5, 0))
            RoundedButton(self.content, text='测试连接', command=self._test).grid(row=13, column=1, sticky='w', pady=(12, 0))
            ttk.Label(self.content, text='测试会发起真实请求，可能产生费用。', style='CardDetail.TLabel').grid(row=14, column=1, sticky='w', pady=(4, 0))
            ttk.Label(self.content, textvariable=self.status, style='CardDetail.TLabel', wraplength=440).grid(row=15, column=1, sticky='w', pady=(4, 0))
            RoundedButton(self.content, text='删除连接', command=self._delete).grid(row=17, column=1, sticky='w', pady=(12, 0))
        if c.id != self.state.active_id:
            RoundedButton(self.content, text='设为当前连接', command=self._activate).grid(row=16, column=1, sticky='w', pady=(18, 0))

    def _vendor_selected(self, _event=None):
        vendor = self.values['vendor'].get()
        presets = {'DeepSeek': ('https://api.deepseek.com', 'deepseek-v4-pro'), 'OpenAI': ('https://api.openai.com/v1', '')}
        if vendor in presets:
            self.values['base_url'].set(presets[vendor][0])
            self.values['model'].set(presets[vendor][1])

    def _activate(self):
        self._capture()
        self.state.active_id = self.selected_id
        self._refresh_list()
        self._show_connection()

    def _test(self):
        self._capture()
        c = replace(self._connection())
        try:
            key = (self.context.secrets.get_api_key(c.id) if c.id == 'legacy-api' and os.environ.get('BLOGPOST_API_KEY')
                   else self.state.keys.get(c.id) or self.context.secrets.get_api_key(c.id))
            if not c.base_url or not c.model or not key:
                raise ValueError('请先填写地址、模型和 API Key')
        except Exception as exc:
            self.status.set(str(exc))
            return
        self.status.set('正在测试连接…')
        tested_values = tuple(self.values[name].get() for name in ('base_url', 'model', 'key'))
        results = queue.Queue()
        def run():
            try:
                OpenAICompatibleClient(c.base_url, c.model, key, timeout=20, max_retries=0).complete([{'role': 'user', 'content': 'Reply OK.'}])
                results.put('连接测试成功')
            except Exception:
                results.put('连接测试失败，请检查地址、模型、密钥和网络。')
        def poll():
            if not self.winfo_exists():
                return
            try:
                result = results.get_nowait()
            except queue.Empty:
                self.after(150, poll)
            else:
                current_values = tuple(self.values[name].get() for name in ('base_url', 'model', 'key'))
                if self.selected_id == c.id and self.page == 'model' and current_values == tested_values:
                    self.status.set(result)
        threading.Thread(target=run, daemon=True).start()
        self.after(150, poll)

    def _save(self):
        try:
            self._capture()
            self.state.dry_run = self.dry_run.get()
            cfg = self.state.configuration()
            path = config_path()
            # Preserve pre-migration data before the first new-format save.
            if path.exists() and 'connections' not in json.loads(path.read_text(encoding='utf-8')):
                backup = path.with_suffix(path.suffix + '.pre-model-connections.bak')
                if not backup.exists():
                    shutil.copy2(path, backup)
            store = self.context.secrets
            snapshots = {}
            try:
                for connection_id, value in self.state.keys.items():
                    key_path = store._path_for(connection_id)
                    snapshots[key_path] = key_path.read_bytes() if key_path.exists() else None
                    if connection_id == 'legacy-api' and key_path.exists():
                        backup = key_path.with_suffix(key_path.suffix + '.pre-model-connections.bak')
                        if not backup.exists():
                            shutil.copy2(key_path, backup)
                    store.set_api_key(value, connection_id)
                for connection_id in self.state.deleted_ids:
                    key_path = store._path_for(connection_id)
                    snapshots[key_path] = key_path.read_bytes() if key_path.exists() else None
                    if key_path.exists():
                        backup = key_path.with_name(key_path.name + '.deleted-' + uuid4().hex + '.bak')
                        shutil.copy2(key_path, backup)
                        store.delete_api_key(connection_id)
                cfg.save(path)
            except Exception:
                for key_path, previous in snapshots.items():
                    if previous is None:
                        key_path.unlink(missing_ok=True)
                    else:
                        rollback = key_path.with_suffix(key_path.suffix + '.rollback')
                        rollback.write_bytes(previous)
                        rollback.replace(key_path)
                raise
            self.context.config = cfg
            self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror('设置未保存', str(exc), parent=self)

    def _place_in_work_area(self):
        from blogpost.ui.settings_dialog import fit_dialog_geometry, _Rect
        from ctypes import byref, windll
        import sys
        rect = _Rect()
        if sys.platform == 'win32' and windll.user32.SystemParametersInfoW(0x0030, 0, byref(rect), 0):
            area = (rect.left, rect.top, rect.right, rect.bottom)
        else:
            area = (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        parent = (self.master.winfo_rootx(), self.master.winfo_rooty(), self.master.winfo_width(), self.master.winfo_height())
        width, height, x, y = fit_dialog_geometry(parent, area, preferred=(900, 720))
        self.minsize(min(650, width), min(440, height))
        self.geometry(f'{width}x{height}+{x}+{y}')
