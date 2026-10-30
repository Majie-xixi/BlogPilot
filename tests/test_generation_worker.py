from queue import Queue
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock

from blogpost.config import AppConfig
from blogpost.domain import PublishResult, RunStatus
from blogpost.pipeline import PublishingPipeline
from blogpost.ui.main_window import MainWindow


class GenerationWorkerTests(unittest.TestCase):
    def test_service_status_does_not_infer_model_from_general_network(self):
        from blogpost.ui.main_window import format_service_status
        self.assertEqual(format_service_status('未检测', '不可用'), '模型服务：未检测 · 51CTO：不可用')

    def test_finish_progress_reports_outcome_without_100_percent(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        window = MainWindow.__new__(MainWindow)
        window.progress_step_var = tk.StringVar(root)
        window.progress_pct_var = tk.StringVar(root)
        window._complete_progress('已跳过')
        self.assertEqual(window.progress_step_var.get(), '已跳过')
        self.assertEqual(window.progress_pct_var.get(), '已结束')

    def test_skipped_run_does_not_claim_generation_is_running(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        window = MainWindow.__new__(MainWindow)
        window.running = True
        window.run_button = ttk.Button(root)
        window.batch_button = ttk.Button(root)
        window.hero_title_var = tk.StringVar(root, value='正在生成今天的 AI 技术博文')
        window.progress_var = tk.StringVar(root)
        window._complete_progress = Mock()
        window._append_log = Mock()
        window.refresh = Mock()
        window._finish_run(PublishResult(RunStatus.SKIPPED, message='另一个生成发布任务正在运行'))
        self.assertNotIn('正在生成', window.hero_title_var.get())
        self.assertIn('已跳过', window.progress_var.get())

    def test_pipeline_exception_finishes_ui_and_restores_buttons(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        window = MainWindow.__new__(MainWindow)
        window.root = root
        window.queue = Queue()
        window.running = True
        window.run_button = ttk.Button(root, text="生成中…", state="disabled")
        window.batch_button = ttk.Button(root, state="disabled")
        window.progress_var = tk.StringVar(root)
        window.hero_title_var = tk.StringVar(root)
        window._complete_progress = Mock()
        window._append_log = Mock()
        window.refresh = Mock()
        window._show_task_failure = Mock()
        pipeline = PublishingPipeline(
            AppConfig(model=""), None, None, None, None, None, None, None, None, None, None
        )

        try:
            window._run_worker(pipeline, False)
        except Exception as exc:
            self.fail(f"worker exception escaped without notifying UI: {exc}")

        event = window.queue.get_nowait()
        self.assertEqual(event[0], "done")
        self.assertEqual(event[1].status, RunStatus.FAILED)
        self.assertEqual(event[1].message, "model is required")
        window.queue.put(event)
        window._drain_queue()

        self.assertFalse(window.running)
        self.assertEqual(str(window.run_button["state"]), "normal")
        self.assertEqual(str(window.batch_button["state"]), "normal")
        self.assertEqual(window.run_button["text"], "立即生成并发布 →")
        self.assertIn("model is required", window.progress_var.get())
        window._show_task_failure.assert_called_once_with("model is required", uncertain=False)


if __name__ == "__main__":
    unittest.main()
