import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from blogpost.application import build_context
from blogpost.domain import PublishResult, RunStatus
from blogpost.ui.main_window import MainWindow
from blogpost.ui.theme import configure_theme


class MainWindowSmokeTests(unittest.TestCase):
    def test_running_stop_button_stays_within_panel_at_supported_window_sizes(self):
        for geometry in ('1040x740+30+30', '900x660+30+30'):
            with self.subTest(geometry=geometry), tempfile.TemporaryDirectory() as root_dir:
                with patch.dict('os.environ', {'BLOGPILOT_DATA_DIR': root_dir}):
                    context = build_context()
                    root = tk.Tk()
                    root.geometry(geometry)
                    try:
                        configure_theme(root)
                        with patch.object(MainWindow, '_start_runtime_status_refresh'):
                            window = MainWindow(root, context)
                            root.update()
                            with patch.object(window, '_network_preflight', return_value=True), \
                                 patch.object(context.repository, 'has_successful_publication', return_value=False), \
                                 patch('blogpost.application.ApplicationContext.build_pipeline'), \
                                 patch('blogpost.ui.main_window.threading.Thread'):
                                window.run_now()
                            root.update()
                            button = window.cancel_button
                            panel = button.master.master.master
                            def assert_inside():
                                self.assertGreater(button.winfo_width(), 1)
                                for ancestor in (button.master, button.master.master, panel):
                                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), ancestor.winfo_rooty() + ancestor.winfo_height())
                                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), ancestor.winfo_rootx() + ancestor.winfo_width())
                                progress = window.progress_frame
                                self.assertLessEqual(progress.winfo_rooty() + progress.winfo_height(), panel.winfo_rooty() + panel.winfo_height())
                            assert_inside()
                            window.cancel_run()
                            root.update()
                            assert_inside()
                            with patch.object(window, 'refresh'):
                                window._finish_run(PublishResult(RunStatus.SKIPPED, message='已取消'))
                            root.update()
                            self.assertEqual(button.winfo_manager(), '')
                    finally:
                        for callback_id in root.tk.call('after', 'info'):
                            root.after_cancel(callback_id)
                        root.destroy()

    def test_batch_stop_button_stays_within_panel(self):
        with tempfile.TemporaryDirectory() as root_dir, patch.dict('os.environ', {'BLOGPILOT_DATA_DIR': root_dir}):
            context = build_context()
            root = tk.Tk()
            root.geometry('900x660+30+30')
            try:
                configure_theme(root)
                with patch.object(MainWindow, '_start_runtime_status_refresh'):
                    window = MainWindow(root, context)
                    root.update()
                    with patch('blogpost.ui.main_window.threading.Thread'):
                        window._start_batch([context.account().id])
                    root.update()
                    button = window.cancel_button
                    panel = button.master.master.master
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), panel.winfo_rooty() + panel.winfo_height())
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), panel.winfo_rootx() + panel.winfo_width())
                    with patch.object(window, 'refresh'), patch.object(window, '_show_batch_summary'):
                        window._finish_batch([])
                    root.update()
                    self.assertEqual(button.winfo_manager(), '')
            finally:
                for callback_id in root.tk.call('after', 'info'):
                    root.after_cancel(callback_id)
                root.destroy()

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
