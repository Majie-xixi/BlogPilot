from pathlib import Path
import tempfile
import unittest

from blogpost.run_lock import AlreadyRunning, RunLock


class RunLockTests(unittest.TestCase):
    def test_second_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run.lock"
            with RunLock(path):
                with self.assertRaises(AlreadyRunning):
                    with RunLock(path):
                        pass
            with RunLock(path):
                pass
