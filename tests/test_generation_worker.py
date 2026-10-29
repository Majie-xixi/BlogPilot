from queue import Queue
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock

from blogpost.config import AppConfig
from blogpost.domain import RunStatus
from blogpost.pipeline import PublishingPipeline
from blogpost.ui.main_window import MainWindow


class GenerationWorkerTests(unittest.TestCase):
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
        window._complete_progress = Mock()
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
