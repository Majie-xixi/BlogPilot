from datetime import time
from pathlib import Path
import unittest

from blogpost.scheduler import WindowsTaskScheduler


class SchedulerTests(unittest.TestCase):
    def test_install_script_has_daily_time_and_start_when_available(self):
        scheduler = WindowsTaskScheduler(
            executable=Path(r"E:\app\BlogPostPublisher.exe"),
            working_dir=Path(r"E:\app"),
        )
        script = scheduler.build_install_script(time(10, 0))
        self.assertIn("10:00", script)
        self.assertIn("StartWhenAvailable", script)
        self.assertIn("run-daily", script)
        self.assertIn("BlogPostPublisher-Daily", script)
