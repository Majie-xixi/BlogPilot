import json
import unittest
from urllib.error import HTTPError

from blogpost.llm.client import LlmAuthError, OpenAICompatibleClient
from blogpost.llm.generation import ArticleGenerator, TopicPlanner
from blogpost.corpus import CorpusItem
from pathlib import Path


class LlmTests(unittest.TestCase):
    def test_client_parses_chat_completion(self):
        def transport(url, headers, payload, timeout):
            return {
                "choices": [{"message": {"content": "生成结果"}}],
                "usage": {"total_tokens": 12},
            }

        client = OpenAICompatibleClient("https://example/v1", "model", "key", transport=transport)
        self.assertEqual(client.complete([{"role": "user", "content": "你好"}]), "生成结果")

    def test_client_maps_authentication_error(self):
        def transport(url, headers, payload, timeout):
            raise HTTPError(url, 401, "Unauthorized", {}, None)

        client = OpenAICompatibleClient("https://example/v1", "model", "bad", transport=transport)
        with self.assertRaises(LlmAuthError):
            client.complete([{"role": "user", "content": "你好"}])

    def test_topic_planner_rejects_historical_duplicate(self):
        class FakeClient:
            def complete(self, messages, **kwargs):
                return json.dumps(
                    {
                        "candidates": [
                            {"title": "AI Agent 实战", "summary": "重复主题", "direction": "Agent"},
                            {"title": "AIOps 告警降噪的规则与模型协作", "summary": "告警降噪工程设计", "direction": "AIOps"},
                        ]
                    },
                    ensure_ascii=False,
                )

        history = [CorpusItem(Path("old.md"), "AI Agent 实战", "# AI Agent 实战\n内容", "hash")]
        topic = TopicPlanner(FakeClient()).choose(history, 0.76, 0.68)
        self.assertEqual(topic.title, "AIOps 告警降噪的规则与模型协作")

    def test_article_generator_accepts_fenced_markdown(self):
        class FakeClient:
            def complete(self, messages, **kwargs):
                return "```markdown\n# 新标题\n\n正文内容\n```"

        article = ArticleGenerator(FakeClient()).generate(
            title="新标题",
            summary="摘要",
            style_summary="风格简洁",
        )
        self.assertEqual(article.title, "新标题")
        self.assertTrue(article.markdown.startswith("# 新标题"))
