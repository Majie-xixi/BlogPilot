from pathlib import Path
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
from blogpost.domain import Account
from blogpost.publishers.cto51 import (
    Cto51Publisher,
    HOME_URL,
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
    def test_installed_supported_browser_is_found(self):
        browser = find_supported_browser()
        path = browser.executable
        self.assertTrue(path.exists())
        self.assertIn(browser.name, {"Chrome", "Edge"})
        self.assertIn(path.name.lower(), {"chrome.exe", "msedge.exe"})

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
        ):
            publisher = context.publisher_for_account(account.id)

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
