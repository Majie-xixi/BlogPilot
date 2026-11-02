from pathlib import Path
import tempfile
import unittest

from blogpost.db import Database
from blogpost.repositories import Repository
from blogpost.sensitive_words import effective_sensitive_words


class SensitiveWordStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.db")
        self.db.initialize()
        self.repo = Repository(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def words(self) -> dict[str, str | None]:
        return {row["term"]: row["replacement"] for row in self.repo.list_sensitive_words()}

    def test_record_inserts_and_counts_hits(self):
        self.repo.record_sensitive_word("外链挂马")
        self.repo.record_sensitive_word("外链挂马")
        rows = self.repo.list_sensitive_words()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hit_count"], 2)
        self.assertEqual(rows[0]["source"], "auto")

    def test_blank_term_is_ignored(self):
        self.repo.record_sensitive_word("   ")
        self.assertEqual(self.repo.list_sensitive_words(), [])

    def test_manual_replacement_fills_empty_and_survives_later_auto_hits(self):
        self.repo.record_sensitive_word("灰产")
        self.assertIsNone(self.words()["灰产"])
        self.repo.record_sensitive_word("灰产", "灰色产业", source="manual")
        self.assertEqual(self.words()["灰产"], "灰色产业")
        self.repo.record_sensitive_word("灰产")
        self.assertEqual(self.words()["灰产"], "灰色产业")

    def test_local_words_merge_with_builtin_baseline(self):
        self.repo.record_sensitive_word("外链挂马", "外部资源劫持")
        merged = effective_sensitive_words(self.words())
        self.assertEqual(merged["外链挂马"], "外部资源劫持")
        self.assertEqual(merged["木马"], "恶意程序")

    def test_initialize_is_idempotent_for_new_table(self):
        self.db.initialize()
        self.repo.record_sensitive_word("灰产")
        self.assertEqual(len(self.repo.list_sensitive_words()), 1)
