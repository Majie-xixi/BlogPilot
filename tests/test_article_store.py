from datetime import date
from pathlib import Path
import tempfile
import unittest

from blogpost.article_store import ArticleStore


class ArticleStoreTests(unittest.TestCase):
    def test_store_creates_directory_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "generated_posts"
            store = ArticleStore(output)
            first = store.save("标题", "# 标题\n内容", date(2026, 7, 15))
            second = store.save("标题", "# 标题\n不同内容", date(2026, 7, 15))
            self.assertTrue(first.path.exists())
            self.assertTrue(second.path.exists())
            self.assertNotEqual(first.path, second.path)
            self.assertNotEqual(first.sha256, second.sha256)
