import json
import unittest

from blogpost.llm.review import ModelReviewer


class ReviewerTests(unittest.TestCase):
    def test_structured_review_is_parsed(self):
        class FakeClient:
            def complete(self, messages, **kwargs):
                return json.dumps(
                    {
                        "passed": True,
                        "score": 88,
                        "issues": [],
                    }
                )

        report = ModelReviewer(FakeClient()).review("# 标题\n正文")
        self.assertTrue(report.passed)
        self.assertEqual(report.score, 88)

    def test_invalid_review_fails_closed(self):
        class FakeClient:
            def complete(self, messages, **kwargs):
                return "not json"

        report = ModelReviewer(FakeClient()).review("# 标题\n正文")
        self.assertFalse(report.passed)
        self.assertEqual(report.issues[0].code, "review_parse_error")

    def test_reviewer_checks_platform_sensitive_wording(self):
        class CapturingClient:
            prompt = ""

            def complete(self, messages, **kwargs):
                self.prompt = "\n".join(message["content"] for message in messages)
                return json.dumps({"passed": True, "score": 90, "issues": []})

        client = CapturingClient()

        ModelReviewer(client).review("# 标题\n正文")

        self.assertIn("platform_sensitive_wording", client.prompt)
        self.assertIn("社区审核", client.prompt)
