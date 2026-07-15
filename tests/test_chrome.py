from pathlib import Path
import tempfile
import unittest

from blogpost.browser.chrome import ChromeController, find_chrome
from blogpost.browser.websocket import encode_text_frame
from blogpost.publishers.cto51 import build_fill_script


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

    def test_websocket_client_frames_are_masked(self):
        frame = encode_text_frame("hello", mask_key=b"1234")
        self.assertEqual(frame[0], 0x81)
        self.assertTrue(frame[1] & 0x80)

    def test_fill_script_json_escapes_markdown(self):
        script = build_fill_script('标题"一', "# 标题\n```python\nprint('x')\n```", "AI 智能体")
        self.assertIn("标题\\\"一", script)
        self.assertIn("AI 智能体", script)
        self.assertIn("dry", script)
