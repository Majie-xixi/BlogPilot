import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from blogpost.application import build_context
from blogpost.ui.main_window import MainWindow
from blogpost.ui.theme import configure_theme


class MainWindowSmokeTests(unittest.TestCase):
    def test_window_builds_with_service_status_and_stop_control(self):
        with tempfile.TemporaryDirectory() as root_dir:
            with patch.dict('os.environ', {'BLOGPILOT_DATA_DIR': root_dir}):
                context = build_context()
                root = tk.Tk()
                root.withdraw()
                try:
                    configure_theme(root)
                    with patch.object(MainWindow, '_start_runtime_status_refresh'):
                        window = MainWindow(root, context)
                        root.update_idletasks()
                    self.assertIn('模型服务：未检测', window.service_status_var.get())
                    self.assertIn('51CTO：未检查', window.service_status_var.get())
                    self.assertEqual(window.cancel_button.winfo_manager(), '')
                finally:
                    for callback_id in root.tk.call('after', 'info'):
                        root.after_cancel(callback_id)
                    root.destroy()
