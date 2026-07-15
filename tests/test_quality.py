import unittest

from blogpost.corpus import CorpusItem
from blogpost.quality import QualityGate
from pathlib import Path


class QualityTests(unittest.TestCase):
    def test_valid_ai_article_passes(self):
        content = "# AIOps 告警治理\n\n" + ("人工智能运维通过日志分析与告警聚合降低噪声。" * 120)
        report = QualityGate(min_chinese_chars=401).check(content, [])
        self.assertTrue(report.passed, report.issues)

    def test_short_or_unbalanced_article_fails(self):
        content = "# AI 测试\n\n内容太短\n```python\nprint(1)"
        report = QualityGate(min_chinese_chars=401).check(content, [])
        codes = {issue.code for issue in report.issues}
        self.assertIn("too_short", codes)
        self.assertIn("unbalanced_fence", codes)

    def test_secret_and_duplicate_are_blocked(self):
        old = "# AI 安全\n\n" + ("提示词安全检查" * 100)
        history = [CorpusItem(Path("old.md"), "AI 安全", old, "hash")]
        content = old + "\napi_key=sk-very-secret-token"
        report = QualityGate(min_chinese_chars=10).check(content, history)
        codes = {issue.code for issue in report.issues}
        self.assertIn("secret", codes)
        self.assertIn("duplicate_title", codes)
