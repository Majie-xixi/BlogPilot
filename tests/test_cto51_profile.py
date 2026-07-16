from datetime import datetime
import unittest

from blogpost.publishers.cto51_profile import (
    parse_51cto_time,
    parse_profile_display_name,
    parse_profile_html,
)
from blogpost.ui.account_dialog import is_generic_account_name


class Cto51ProfileTests(unittest.TestCase):
    def test_parse_profile_display_name_from_title(self):
        html = "<title>马杰的博客_原创文章_51CTO博客</title>"

        self.assertEqual(parse_profile_display_name(html), "马杰")

    def test_parse_profile_display_name_from_json_nickname(self):
        html = '<script>window.data={"nickname":"MJ 技术笔记"}</script>'

        self.assertEqual(parse_profile_display_name(html), "MJ 技术笔记")

    def test_parse_profile_html_includes_display_name(self):
        html = """
        <html>
          <head><title>MJ 技术笔记的博客_51CTO博客</title></head>
          <body></body>
        </html>
        """

        snapshot = parse_profile_html(
            html,
            "https://blog.51cto.com/u_987654",
            now=datetime(2026, 7, 16, 10, 0),
        )

        self.assertEqual(snapshot.display_name, "MJ 技术笔记")

    def test_generic_account_names_are_replaceable(self):
        for name in ("账号 1", "账号2", "账号一", "账号 二"):
            with self.subTest(name=name):
                self.assertTrue(is_generic_account_name(name))
        self.assertFalse(is_generic_account_name("MJ 技术笔记"))

    def test_parse_relative_time_still_works(self):
        now = datetime(2026, 7, 16, 10, 0)

        self.assertEqual(
            parse_51cto_time("1小时前", now),
            datetime(2026, 7, 16, 9, 0),
        )


if __name__ == "__main__":
    unittest.main()
