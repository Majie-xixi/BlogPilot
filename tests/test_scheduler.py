from datetime import time
from pathlib import Path
import unittest
from unittest.mock import patch

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
        self.assertIn("$now=Get-Date", script)
        self.assertIn("AddDays(1)", script)
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertLess(
            script.index("Unregister-ScheduledTask"),
            script.index("Register-ScheduledTask"),
        )
        self.assertIn("run-daily", script)
        self.assertIn("BlogPostPublisher-Daily", script)

    def test_status_script_validates_registered_action_and_last_result(self):
        scheduler = WindowsTaskScheduler(
            executable=Path(r"D:\Python\python.exe"),
            working_dir=Path(r"E:\MJ_Demo\BlogPost"),
            arguments=r'"E:\MJ_Demo\BlogPost\main.py" run-daily',
        )

        script = scheduler.build_status_script()

        self.assertIn("ExecutableMissing", script)
        self.assertIn("ActionMismatch", script)
        self.assertIn("LastTaskResult", script)
        self.assertIn(str(scheduler.executable), script)
        self.assertIn(scheduler.arguments, script)

    def test_status_returns_the_machine_readable_token(self):
        scheduler = WindowsTaskScheduler(
            executable=Path(r"D:\Python\python.exe"),
            working_dir=Path(r"E:\MJ_Demo\BlogPost"),
            arguments=r'"E:\MJ_Demo\BlogPost\main.py" run-daily',
        )

        with patch.object(
            WindowsTaskScheduler,
            "_run",
            return_value="Invalid|ActionMismatch\r\n",
        ):
            status = scheduler.status()

        self.assertEqual(status, "Invalid|ActionMismatch")
