from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Protocol

from blogpost.corpus import CorpusItem
from blogpost.domain import Article
from blogpost.markdown import normalize_single_h1, parse_markdown
from blogpost.similarity import text_similarity, title_similarity


class CompletionClient(Protocol):
    def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str: ...


@dataclass(slots=True, frozen=True)
class Topic:
    title: str
    summary: str
    direction: str


def _strip_fence(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"```(?:json|markdown|md)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else value


class TopicPlanner:
    def __init__(
        self,
        client: CompletionClient,
        article_type: str = "",
        content_directions: str = "",
        keywords: str = "",
    ):
        self.client = client
        self.article_type = article_type.strip()
        self.content_directions = content_directions.strip()
        self.keywords = keywords.strip()

    def choose(
        self,
        corpus: list[CorpusItem],
        title_threshold: float,
        content_threshold: float,
    ) -> Topic:
        history = "\n".join(f"- {item.title}" for item in corpus[-80:])
        directions = self.content_directions or "AI Agent、AI 编程、Prompt、AIOps、边缘 AI、大模型工程"
        type_hint = self.article_type or "技术解析"
        keyword_hint = (
            f"文章主题必须围绕这些关键词展开：{self.keywords}；标题或摘要必须明确体现这些关键词。"
            if self.keywords
            else ""
        )
        prompt = f"""为 51CTO AI 技术博客提出 8 个全新选题。
博文类型：{type_hint}。
范围：{directions}。
{keyword_hint}
禁止：纯新闻、产品软文、虚构亲历、未经验证的性能数字。
历史标题如下，必须避开：
{history}
只返回 JSON：{{"candidates":[{{"title":"...","summary":"...","direction":"..."}}]}}"""
        raw = self.client.complete(
            [{"role": "system", "content": "你是严谨的中文技术编辑。"}, {"role": "user", "content": prompt}],
            temperature=0.8,
            json_mode=True,
        )
        data = json.loads(_strip_fence(raw))
        for candidate in data.get("candidates", []):
            topic = Topic(
                str(candidate.get("title", "")).strip(),
                str(candidate.get("summary", "")).strip(),
                str(candidate.get("direction", "AI")).strip(),
            )
            if not topic.title or not topic.summary:
                continue
            keywords = [
                value.strip().casefold()
                for value in re.split(r"[,，、;；\s]+", self.keywords)
                if value.strip()
            ]
            candidate_text = f"{topic.title} {topic.summary}".casefold()
            if keywords and not all(keyword in candidate_text for keyword in keywords):
                continue
            if any(title_similarity(topic.title, item.title) >= title_threshold for item in corpus):
                continue
            if any(text_similarity(topic.summary, item.content[:1200]) >= content_threshold for item in corpus):
                continue
            return topic
        raise ValueError("模型未能提供不重复的合规选题")


class ArticleGenerator:
    def __init__(self, client: CompletionClient):
        self.client = client

    def generate(self, title: str, summary: str, style_summary: str) -> Article:
        prompt = f"""写一篇新的中文 AI 技术博客。
标题：{title}
方向摘要：{summary}
风格参考（只参考结构和语气，不得复制）：{style_summary}

硬性要求：
1. 输出完整 Markdown，只有一个一级标题；
2. 正文目标 1500–3000 个中文字符，技术逻辑清楚；
3. 可以使用表格、引用和可验证的通用代码；
4. 不得声称作者亲历未提供的项目，不得虚构版本、公司数据、基准数字、引用或链接；
5. 避免“最新、今天、刚刚”等时效性说法；
6. 内容必须与 AI 技术直接相关，不能写成新闻汇总或软文。
只输出 Markdown。"""
        raw = self.client.complete(
            [{"role": "system", "content": "你是重视原创、事实和工程细节的中文技术作者。"}, {"role": "user", "content": prompt}],
            temperature=0.72,
        )
        markdown = normalize_single_h1(_strip_fence(raw), title)
        document = parse_markdown(markdown)
        if not document.title or not document.body:
            raise ValueError("模型没有返回有效 Markdown 文章")
        return Article(document.title, markdown, title)


class ArticleRewriter:
    def __init__(self, client: CompletionClient):
        self.client = client

    def rewrite(self, markdown: str, feedback: str) -> str:
        prompt = f"""根据质量反馈重写下面文章，保留主题但解决所有问题。
反馈：{feedback}
要求仍为原创 AI 技术文章，不得虚构经历或数字，只输出 Markdown。

原文：
{markdown}"""
        return _strip_fence(self.client.complete([{"role": "user", "content": prompt}], temperature=0.5))
