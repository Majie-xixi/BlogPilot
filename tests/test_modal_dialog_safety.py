import tkinter as tk
import time
import unittest

from blogpost.ui.main_window import (
    _recover_hidden_dialog,
    present_modal_dialog,
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

    def test_visible_dialog_keeps_grab(self):
        dialog = tk.Toplevel(self.root)
        dialog.geometry("120x80+40+40")
        present_modal_dialog(self.root, dialog)
        self._wait_mapped(dialog)
        self.assertTrue(dialog.winfo_viewable())
        self.assertIs(self.root.grab_current(), dialog)

    def test_hidden_dialog_releases_grab_and_comes_back(self):
        dialog = tk.Toplevel(self.root)
        dialog.geometry("120x80+40+40")
        present_modal_dialog(self.root, dialog)
        self._wait_mapped(dialog)
        dialog.withdraw()
        self._pump()
        _recover_hidden_dialog(self.root, dialog)
        self._wait_mapped(dialog)
        self.assertIsNone(self.root.grab_current())
        self.assertTrue(dialog.winfo_viewable())

    def test_offscreen_dialog_moves_back_over_root(self):
        dialog = tk.Toplevel(self.root)
        present_modal_dialog(self.root, dialog)
        self._pump()
        dialog.geometry("+9000+9000")
        self._pump()
        _recover_hidden_dialog(self.root, dialog)
        self._pump()
        self.assertLess(dialog.winfo_rootx(), self.root.winfo_screenwidth())
        self.assertLess(dialog.winfo_rooty(), self.root.winfo_screenheight())

    def test_auto_close_destroys_dialog_after_timeout(self):
        dialog = tk.Toplevel(self.root)
        present_modal_dialog(self.root, dialog, auto_close_ms=30)
        deadline = time.monotonic() + 3
        while dialog.winfo_exists() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(dialog.winfo_exists())
