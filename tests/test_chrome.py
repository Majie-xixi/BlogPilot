from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from blogpost.application import ApplicationContext
from blogpost.browser.chrome import (
    BrowserInstallation,
    ChromeController,
    find_chrome,
    find_supported_browser,
)
from blogpost.browser.websocket import encode_text_frame
from blogpost.domain import Account, RunStatus
from blogpost.publishers.cto51 import (
    Cto51Publisher,
    HOME_URL,
    PUBLISH_URL,
    build_fill_script,
    build_settings_script,
)


class FakeProfileSession:
    def __init__(self, _websocket_url):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def evaluate(self, _expression):
        return "https://blog.51cto.com/u_123456"


class ChromeTests(unittest.TestCase):
    def test_chrome_is_preferred_when_both_browsers_exist(self):
        chrome_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

        with patch("blogpost.browser.chrome.Path.exists", return_value=True):
            browser = find_supported_browser()

        self.assertEqual(browser.name, "Chrome")
        self.assertEqual(browser.executable, chrome_path)

    def test_edge_is_used_when_chrome_is_missing(self):
        edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

        def exists(path):
            return str(path).lower() == str(edge_path).lower()

        with patch("blogpost.browser.chrome.Path.exists", exists):
            browser = find_supported_browser()

        self.assertEqual(browser.name, "Edge")
        self.assertEqual(browser.executable, edge_path)

    def test_missing_supported_browser_has_clear_error(self):
        with patch("blogpost.browser.chrome.Path.exists", return_value=False):
            with self.assertRaisesRegex(FileNotFoundError, "Chrome.*Edge"):
                find_supported_browser()

    def test_find_chrome_keeps_legacy_path_alias(self):
        edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

        def exists(path):
            return str(path).lower() == str(edge_path).lower()

        with patch("blogpost.browser.chrome.Path.exists", exists):
            self.assertEqual(find_chrome(), edge_path)

    def test_launch_arguments_use_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as root:
            controller = ChromeController(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(root) / "profile",
                browser_name="Edge",
            )
            args = controller.build_launch_args(9229, "https://blog.51cto.com")
            joined = " ".join(args)
            self.assertIn("--remote-debugging-port=9229", joined)
            self.assertIn(str(Path(root) / "profile"), joined)
            self.assertNotIn("User Data\\Default", joined)
            self.assertIn("--disable-component-update", args)
            self.assertIn("--disable-background-networking", args)
            self.assertIn("--disable-sync", args)

    def test_controller_uses_account_specific_default_port(self):
        with tempfile.TemporaryDirectory() as root:
            controller = ChromeController(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(root) / "account-2",
                default_port=9230,
            )

            args = controller.build_launch_args(
                controller.default_port,
                "https://blog.51cto.com/login",
            )

            self.assertIn("--remote-debugging-port=9230", args)

    def test_available_port_skips_a_listener_on_the_preferred_port(self):
        with tempfile.TemporaryDirectory() as root, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            occupied = listener.getsockname()[1]
            controller = ChromeController(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(root) / "profile",
                default_port=occupied,
            )

            selected = controller.find_available_port(occupied, attempts=2)

        self.assertEqual(selected, occupied + 1)

    def test_start_does_not_attach_to_an_unknown_existing_debug_port(self):
        with tempfile.TemporaryDirectory() as root:
            controller = ChromeController(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(root) / "profile",
                default_port=9229,
            )
            with (
                patch.object(controller, "find_available_port", return_value=9230),
                patch("blogpost.browser.chrome.subprocess.Popen") as popen,
                patch.object(controller, "version", return_value={"Browser": "Chrome"}),
            ):
                selected = controller.start("https://blog.51cto.com")

        self.assertEqual(selected, 9230)
        self.assertIn("--remote-debugging-port=9230", popen.call_args.args[0])

    def test_second_account_publisher_uses_a_different_port(self):
        account = Account(
            id="account-two",
            display_name="账号二",
            sort_order=1,
        )

        class RepositoryStub:
            @staticmethod
            def get_account(_account_id):
                return account

        context = ApplicationContext(
            config=None,
            repository=RepositoryStub(),
            secrets=None,
            chrome=None,
            publisher=None,
            scheduler=None,
        )
        with patch(
            "blogpost.application.find_supported_browser",
            return_value=BrowserInstallation(
                "Chrome",
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ),
        ), patch(
            "blogpost.application.browser_profile_dir",
            return_value=Path(r"E:\profiles\account-two"),
        ) as profile_dir:
            publisher = context.publisher_for_account(account.id)

        profile_dir.assert_called_once_with(account.id, "Chrome")
        self.assertEqual(publisher.chrome.default_port, 9230)
        self.assertEqual(publisher.chrome.profile_dir, Path(r"E:\profiles\account-two"))

    def test_current_profile_url_reuses_existing_51cto_page(self):
        class ChromeStub:
            port = 9229

            def __init__(self):
                self.opened = []

            def list_targets(self):
                return [
                    {
                        "type": "page",
                        "url": "https://blog.51cto.com/login",
                        "webSocketDebuggerUrl": "ws://profile",
                    }
                ]

            def open_tab(self, url):
                self.opened.append(url)
                raise AssertionError("should reuse existing page")

        chrome = ChromeStub()
        publisher = Cto51Publisher(chrome, Path("diagnostics"))

        with patch("blogpost.publishers.cto51.CdpSession", FakeProfileSession):
            url = publisher.current_profile_url()

        self.assertEqual(url, "https://blog.51cto.com/u_123456")
        self.assertEqual(chrome.opened, [])

    def test_current_profile_url_opens_home_once_when_needed(self):
        class ChromeStub:
            port = 9229

            def __init__(self):
                self.opened = []

            def list_targets(self):
                return []

            def open_tab(self, url):
                self.opened.append(url)
                return {"type": "page", "url": url, "webSocketDebuggerUrl": "ws://home"}

        chrome = ChromeStub()
        publisher = Cto51Publisher(chrome, Path("diagnostics"))

        with patch("blogpost.publishers.cto51.CdpSession", FakeProfileSession), patch.object(
            Cto51Publisher,
            "_wait_page_content",
            return_value=None,
        ):
            url = publisher.current_profile_url()

        self.assertEqual(url, "https://blog.51cto.com/u_123456")
        self.assertEqual(chrome.opened, [HOME_URL])

    def test_websocket_client_frames_are_masked(self):
        frame = encode_text_frame("hello", mask_key=b"1234")
        self.assertEqual(frame[0], 0x81)
        self.assertTrue(frame[1] & 0x80)

    def test_fill_script_json_escapes_markdown(self):
        script = build_fill_script('标题"一', "# 标题\n```python\nprint('x')\n```", "AI 智能体")
        self.assertIn("标题\\\"一", script)
        self.assertIn("AI 智能体", script)
        self.assertIn("Object.getOwnPropertyDescriptor", script)
        self.assertIn("textarea.write-area", script)

    def test_settings_script_selects_article_and_personal_categories(self):
        script = build_settings_script("AI 智能体")
        self.assertIn("编程 Agent", script)
        self.assertIn("#selfType", script)
        self.assertIn("personalOk", script)
        self.assertIn("secondaryOk", script)

    def test_sensitive_review_dialog_is_confirmed_without_reporting_success(self):
        class Session:
            @staticmethod
            def evaluate(expression):
                if "继续发布" in expression:
                    return {
                        "detected": True,
                        "clicked": True,
                        "term": "示例词",
                    }
                return {"url": PUBLISH_URL, "text": ""}

        result = Cto51Publisher._wait_publish_result(Session(), timeout=0.1)

        self.assertEqual(result.status, RunStatus.UNKNOWN)
        self.assertIn("等待 51CTO 审核", result.message)
        self.assertIn("示例词", result.message)
