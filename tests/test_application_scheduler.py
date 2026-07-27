from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from blogpost import __version__, application


class ApplicationSchedulerTests(unittest.TestCase):
    def test_source_scheduler_uses_main_launcher(self):
        with patch.object(application.sys, "frozen", False, create=True):
            scheduler = application.scheduler_for_runtime()

        project_root = Path(application.__file__).resolve().parents[2]
        self.assertEqual(scheduler.executable, Path(sys.executable))
        self.assertEqual(scheduler.working_dir, project_root)
        self.assertEqual(
            scheduler.arguments,
            f'"{project_root / "main.py"}" run-daily',
        )

    def test_frozen_scheduler_uses_packaged_executable(self):
        executable = Path(r"E:\BlogPilot\BlogPostPublisher.exe")
        with (
            patch.object(application.sys, "frozen", True, create=True),
            patch.object(application.sys, "executable", str(executable)),
        ):
            scheduler = application.scheduler_for_runtime()

        self.assertEqual(scheduler.executable, executable)
        self.assertEqual(scheduler.working_dir, executable.parent)
        self.assertEqual(scheduler.arguments, "run-daily")

    def test_main_launcher_dispatches_cli_arguments(self):
        project_root = Path(application.__file__).resolve().parents[2]

        completed = subprocess.run(
            [sys.executable, str(project_root / "main.py"), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(__version__, completed.stdout)


if __name__ == "__main__":
    unittest.main()
