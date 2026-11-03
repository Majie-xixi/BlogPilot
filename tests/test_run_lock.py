from pathlib import Path
import os
import tempfile
import unittest
import subprocess
import sys

from blogpost.run_lock import AlreadyRunning, RunLock


class RunLockTests(unittest.TestCase):
    def test_crashed_owner_can_be_recovered_but_live_owner_is_protected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'run.lock'
            script = ("import os,sys; from blogpost.run_lock import RunLock; "
                      "lock=RunLock(sys.argv[1]); lock.__enter__(); "
                      "print('ready', flush=True); sys.stdin.readline(); os._exit(0)")
            child = subprocess.Popen([sys.executable, '-u', '-c', script, str(path)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                with self.assertRaises(AlreadyRunning):
                    with RunLock(path):
                        pass
                child.stdin.write('\n')
                child.stdin.flush()
                self.assertEqual(child.wait(timeout=10), 0)
                with RunLock(path):
                    self.assertEqual(path.read_text(encoding='ascii'), str(os.getpid()))
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                child.stdin.close()
                child.stdout.close()

    def test_lock_from_exited_process_is_recovered(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'run.lock'
            process = subprocess.Popen([sys.executable, '-c', 'pass'])
            process.wait(timeout=10)
            path.write_text(str(process.pid), encoding='ascii')
            with RunLock(path):
                self.assertEqual(path.read_text(encoding='ascii'), str(os.getpid()))
                with self.assertRaises(AlreadyRunning):
                    with RunLock(path):
                        pass
            self.assertFalse(path.exists())

    def test_invalid_lock_is_not_discarded(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'run.lock'
            path.write_text('invalid', encoding='ascii')
            with self.assertRaises(AlreadyRunning):
                with RunLock(path):
                    pass
            self.assertEqual(path.read_text(encoding='ascii'), 'invalid')

    def test_second_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run.lock"
            with RunLock(path):
                with self.assertRaises(AlreadyRunning):
                    with RunLock(path):
                        pass
            with RunLock(path):
                pass
