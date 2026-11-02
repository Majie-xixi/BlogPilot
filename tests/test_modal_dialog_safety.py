import tkinter as tk
import time
import unittest

from blogpost.ui.main_window import (
    _recover_hidden_dialog,
    present_modal_dialog,
    safe_destroy_dialog,
)


class ModalDialogSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("240x160+20+20")

    def tearDown(self):
        # 直接用 Tcl 层取消定时器：tkinter 的 after_cancel 会顺带删除回调命令，
        # 与随后 destroy 时的清理重复，触发 "can't delete Tcl command"。
        for callback_id in self.root.tk.call("after", "info"):
            try:
                self.root.tk.call("after", "cancel", callback_id)
            except tk.TclError:
                pass
        self.root.destroy()

    def _pump(self, seconds: float = 0.1) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.005)

    def _wait_mapped(self, widget: tk.Misc, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while not widget.winfo_viewable() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def test_default_non_modal_keeps_root_accessible_without_grab(self):
        dialog = tk.Toplevel(self.root)
        dialog.geometry("120x80+40+40")
        present_modal_dialog(self.root, dialog, modal=False)
        self._wait_mapped(dialog)
        self.assertTrue(dialog.winfo_viewable())
        # 默认非模态绝不占用全局 grab，确保主窗口永远不被锁死
        self.assertIsNone(self.root.grab_current())

    def test_modal_mode_keeps_grab_and_recovers_when_hidden(self):
        dialog = tk.Toplevel(self.root)
        dialog.geometry("120x80+40+40")
        present_modal_dialog(self.root, dialog, modal=True)
        self._wait_mapped(dialog)
        self.assertTrue(dialog.winfo_viewable())
        self.assertIs(self.root.grab_current(), dialog)

        dialog.withdraw()
        self._pump()
        _recover_hidden_dialog(self.root, dialog)
        self._wait_mapped(dialog)
        self.assertIsNone(self.root.grab_current())
        self.assertTrue(dialog.winfo_viewable())

    def test_offscreen_dialog_moves_back_over_root(self):
        dialog = tk.Toplevel(self.root)
        present_modal_dialog(self.root, dialog, modal=True)
        self._pump()
        dialog.geometry("+9000+9000")
        self._pump()
        _recover_hidden_dialog(self.root, dialog)
        self._pump()
        self.assertLess(dialog.winfo_rootx(), self.root.winfo_screenwidth())
        self.assertLess(dialog.winfo_rooty(), self.root.winfo_screenheight())

    def test_auto_close_destroys_dialog_after_timeout(self):
        dialog = tk.Toplevel(self.root)
        present_modal_dialog(self.root, dialog, auto_close_ms=30, modal=False)
        deadline = time.monotonic() + 3
        while dialog.winfo_exists() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(dialog.winfo_exists())

    def test_auto_close_destroys_modal_dialog_and_releases_grab(self):
        dialog = tk.Toplevel(self.root)
        present_modal_dialog(self.root, dialog, auto_close_ms=30, modal=True)
        deadline = time.monotonic() + 3
        while dialog.winfo_exists() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNone(self.root.grab_current())

    def test_dialog_destruction_cleans_up_root_map_binding(self):
        initial_binding = self.root.bind("<Map>") or ""
        dialog = tk.Toplevel(self.root)
        dialog.geometry("120x80+40+40")
        present_modal_dialog(self.root, dialog, modal=False)
        self._wait_mapped(dialog)

        # 存在绑定的证明
        mid_binding = self.root.bind("<Map>") or ""
        self.assertNotEqual(initial_binding, mid_binding)

        # 无论以何种方式销毁弹窗，绑定均自动清除，不泄露内存
        safe_destroy_dialog(dialog)
        self._pump(0.1)

        after_binding = self.root.bind("<Map>") or ""
        self.assertEqual(initial_binding, after_binding)
