from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogpost.application import ApplicationContext
from blogpost.browser.chrome import ChromeController, find_chrome
from blogpost.browser.websocket import encode_text_frame
from blogpost.domain import Account
from blogpost.publishers.cto51 import build_fill_script, build_settings_script


class ChromeTests(unittest.TestCase):
    def test_installed_chrome_is_found(self):
        path = find_chrome()
        self.assertTrue(path.exists())
        self.assertEqual(path.name.lower(), "chrome.exe")

    def test_launch_arguments_use_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as root:
            controller = ChromeController(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(root) / "profile",
            )
            args = controller.build_launch_args(9229, "https://blog.51cto.com")
            joined = " ".join(args)
            self.assertIn("--remote-debugging-port=9229", joined)
            self.assertIn(str(Path(root) / "profile"), joined)
            self.assertNotIn("User Data\\Default", joined)

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
            "blogpost.application.find_chrome",
            return_value=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ), patch(
            "blogpost.application.browser_profile_dir",
            return_value=Path(r"E:\profiles\account-two"),
        ):
            publisher = context.publisher_for_account(account.id)

        self.assertEqual(publisher.chrome.default_port, 9230)
        self.assertEqual(publisher.chrome.profile_dir, Path(r"E:\profiles\account-two"))

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
