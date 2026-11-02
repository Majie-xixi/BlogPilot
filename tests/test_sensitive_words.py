import unittest

from blogpost.quality import QualityGate
from blogpost.sensitive_words import (
    clean_captured_term,
    effective_sensitive_words,
    load_builtin_words,
    merge_sensitive_words,
    scan_sensitive_hits,
)


class BuiltinWordlistTests(unittest.TestCase):
    def test_baseline_file_ships_the_seed_words(self):
        words = load_builtin_words()
        self.assertEqual(words["漏洞"], "风险缺口或薄弱点")
        self.assertEqual(words["木马"], "恶意程序")
        self.assertEqual(words["提权"], "权限异常提升")

    def test_parser_skips_comments_and_blank_lines(self):
        # 基线文件带注释头，能正常解析即说明注释被跳过
        self.assertIn("黑客", load_builtin_words())


class MergeWordlistTests(unittest.TestCase):
    def test_presence_is_union_across_layers(self):
        merged = merge_sensitive_words({"本地词": ""}, {"内置词": "建议"})
        self.assertIn("本地词", merged)
        self.assertIn("内置词", merged)

    def test_local_without_suggestion_keeps_builtin_suggestion(self):
        merged = merge_sensitive_words({"木马": ""}, {"木马": "恶意程序"})
        self.assertEqual(merged["木马"], "恶意程序")

    def test_local_suggestion_overrides_builtin(self):
        merged = merge_sensitive_words({"木马": "本地建议"}, {"木马": "恶意程序"})
        self.assertEqual(merged["木马"], "本地建议")

    def test_effective_words_merges_local_with_builtin(self):
        merged = effective_sensitive_words({"新捕获词": None, "漏洞": "本地叫法"})
        self.assertEqual(merged["新捕获词"], "")
        self.assertEqual(merged["漏洞"], "本地叫法")
        self.assertIn("黑客", merged)


class CapturedTermTests(unittest.TestCase):
    def test_plain_word_is_kept(self):
        self.assertEqual(clean_captured_term("内网横向"), "内网横向")
        self.assertEqual(clean_captured_term("  木马  "), "木马")

    def test_surrounding_quotes_are_stripped(self):
        self.assertEqual(clean_captured_term("“提权”"), "提权")

    def test_sentence_or_long_text_is_rejected(self):
        self.assertIsNone(clean_captured_term("正文包含不当内容涉及安全"))
        self.assertIsNone(clean_captured_term("木 马"))
        self.assertIsNone(clean_captured_term("这" * 9))
        self.assertIsNone(clean_captured_term(""))


class ScanHitsTests(unittest.TestCase):
    def test_hits_are_found_in_text(self):
        words = {"木马": "恶意程序", "提权": ""}
        self.assertEqual(scan_sensitive_hits("文中出现了木马行为", words), ["木马"])
        self.assertEqual(scan_sensitive_hits("干净的文字", words), [])


class QualityGateWordlistTests(unittest.TestCase):
    def test_gate_detects_local_captured_word_with_suggestion(self):
        gate = QualityGate(min_chinese_chars=10, sensitive_words={"外链挂马": "外部资源劫持"})
        report = gate.check("# AI 标题\n\n外链挂马的风险说明。", [])
        issue = next(
            item for item in report.issues if item.code == "platform_sensitive_wording"
        )
        self.assertIn("外链挂马", issue.message)
        self.assertIn("外部资源劫持", issue.message)

    def test_gate_message_uses_neutral_hint_when_no_suggestion(self):
        gate = QualityGate(min_chinese_chars=10, sensitive_words={"灰产": ""})
        report = gate.check("# AI 标题\n\n灰产话题分析。", [])
        issue = next(
            item for item in report.issues if item.code == "platform_sensitive_wording"
        )
        self.assertIn("灰产", issue.message)
        self.assertIn("中性专业表达", issue.message)
