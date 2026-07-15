from pathlib import Path
import tempfile
import unittest

from blogpost.corpus import CorpusIndexer


class CorpusTests(unittest.TestCase):
    def test_generated_directory_is_not_treated_as_history(self):
        with tempfile.TemporaryDirectory() as root:
            history = Path(root)
            (history / "old.md").write_text("# 已发布\n历史内容", encoding="utf-8")
            generated = history / "generated_posts"
            generated.mkdir()
            (generated / "new.md").write_text("# 新文章\n新内容", encoding="utf-8")

            items = CorpusIndexer(history, generated).scan_history()

            self.assertEqual([item.title for item in items], ["已发布"])
