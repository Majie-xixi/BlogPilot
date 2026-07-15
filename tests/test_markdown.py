import unittest

from blogpost.markdown import normalize_single_h1, parse_markdown, safe_filename


class MarkdownTests(unittest.TestCase):
    def test_parser_extracts_title_and_balanced_fences(self):
        doc = parse_markdown("# 标题\n\n正文内容\n\n```python\nprint('ok')\n```\n")
        self.assertEqual(doc.title, "标题")
        self.assertTrue(doc.fences_balanced)
        self.assertGreaterEqual(doc.chinese_chars, 4)

    def test_safe_filename_removes_windows_characters(self):
        self.assertEqual(safe_filename('AI: "工具" / 实战?'), "AI-工具-实战")

    def test_h1_inside_code_fence_is_not_counted_as_article_title(self):
        doc = parse_markdown("# 正文标题\n\n```bash\n# shell 注释\necho ok\n```\n")

        self.assertEqual(doc.heading_count, 1)
        self.assertTrue(doc.fences_balanced)

    def test_normalizer_adds_one_h1_and_demotes_extra_headings(self):
        markdown = normalize_single_h1("# 旧标题\n\n正文\n\n# 另一个标题", "规范标题")
        doc = parse_markdown(markdown)

        self.assertEqual(doc.title, "规范标题")
        self.assertEqual(doc.heading_count, 1)
        self.assertIn("## 另一个标题", markdown)
