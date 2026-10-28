import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from blogpost.browser.chrome import ChromeController


class BrowserReconnectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name) / "account one's profile"

    def test_start_reconnects_after_restart_or_previous_timeout(self):
        for stale_port in (None, 9230):
            with self.subTest(stale_port=stale_port):
                controller = ChromeController(Path(sys.executable), self.profile)
                controller.port = stale_port
                if stale_port:
                    controller.process = Mock()
                    controller.process.poll.return_value = 0
                with (
                    patch.object(controller, "_find_running_profile_port", return_value=9229, create=True),
                    patch.object(controller, "version", return_value={"Browser": "Chrome"}),
                    patch.object(controller, "open_tab") as open_tab,
                    patch("blogpost.browser.chrome.subprocess.Popen", side_effect=AssertionError("must reuse browser")),
                ):
                    port = controller.start("about:blank")

                self.assertEqual(port, 9229)
                self.assertEqual(controller.port, 9229)
                self.assertIsNone(controller.process)
                open_tab.assert_called_once_with("about:blank")

    def test_unhealthy_existing_profile_stops_without_launching_another_browser(self):
        controller = ChromeController(Path(sys.executable), self.profile)
        with (
            patch.object(controller, "_find_running_profile_port", return_value=9229, create=True),
            patch.object(controller, "version", side_effect=URLError("unavailable")),
            patch("blogpost.browser.chrome.subprocess.Popen", side_effect=AssertionError("must not launch")),
        ):
            with self.assertRaisesRegex(ConnectionError, "专用"):
                controller.start("about:blank")

        self.assertIsNone(controller.port)

    def test_ensure_running_opens_requested_page_once_after_reconnection(self):
        controller = ChromeController(Path(sys.executable), self.profile)
        with (
            patch.object(controller, "_find_running_profile_port", return_value=9229, create=True),
            patch.object(controller, "version", return_value={"Browser": "Chrome"}),
            patch.object(controller, "open_tab") as open_tab,
            patch("blogpost.browser.chrome.subprocess.Popen", side_effect=AssertionError("must reuse browser")),
        ):
            self.assertTrue(controller.ensure_running("about:blank"))
            self.assertFalse(controller.ensure_running("about:blank"))

        self.assertEqual(controller.port, 9229)
        open_tab.assert_called_once_with("about:blank")

    def _start_profile_listener(self, advertised_port=None, process_type=None):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        code = (
            "import socket,sys,threading; "
            "listener=socket.socket(); "
            "listener.bind(('127.0.0.1',int(sys.argv[1]))); "
            "listener.listen(); print('READY',flush=True); threading.Event().wait()"
        )
        process = subprocess.Popen(
            [
                sys.executable, "-u", "-c", code, str(port),
                f"--user-data-dir={self.profile}",
                f"--remote-debugging-port={port if advertised_port is None else advertised_port}",
                *([f"--type={process_type}"] if process_type else []),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        def stop_listener():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

        self.addCleanup(stop_listener)
        self.assertEqual(process.stdout.readline().strip(), "READY")
        return port

    @unittest.skipUnless(os.name == "nt", "Windows process ownership probe")
    def test_windows_probe_requires_same_executable_and_profile(self):
        port = self._start_profile_listener()
        matching = ChromeController(Path(sys.executable), self.profile)
        other_account = ChromeController(Path(sys.executable), self.profile.parent / "other-account")
        other_executable = ChromeController(self.profile.parent / "different.exe", self.profile)

        self.assertEqual(matching._find_running_profile_port(), port)
        self.assertIsNone(other_account._find_running_profile_port())
        self.assertIsNone(other_executable._find_running_profile_port())

    @unittest.skipUnless(os.name == "nt", "Windows process ownership probe")
    def test_windows_probe_rejects_port_owned_by_another_process(self):
        with socket.socket() as unrelated:
            unrelated.bind(("127.0.0.1", 0))
            unrelated.listen()
            self._start_profile_listener(advertised_port=unrelated.getsockname()[1])
            controller = ChromeController(Path(sys.executable), self.profile)

            with self.assertRaisesRegex(ConnectionError, "专用"):
                controller._find_running_profile_port()

    @unittest.skipUnless(os.name == "nt", "Windows process ownership probe")
    def test_windows_probe_ignores_browser_child_processes(self):
        self._start_profile_listener(process_type="renderer")
        controller = ChromeController(Path(sys.executable), self.profile)

        self.assertIsNone(controller._find_running_profile_port())

    @unittest.skipUnless(os.name == "nt", "Windows process ownership probe")
    def test_probe_timeout_does_not_launch_an_unverified_browser(self):
        controller = ChromeController(Path(sys.executable), self.profile)
        with (
            patch("blogpost.browser.chrome.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 8)),
            patch("blogpost.browser.chrome.subprocess.Popen", side_effect=AssertionError("must not launch")),
        ):
            with self.assertRaisesRegex(ConnectionError, "检查"):
                controller.start("about:blank")


if __name__ == "__main__":
    unittest.main()
