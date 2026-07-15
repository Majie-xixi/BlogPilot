from __future__ import annotations

from hashlib import sha256
import re

from blogpost.corpus import CorpusItem
from blogpost.domain import QualityIssue, QualityReport
from blogpost.markdown import parse_markdown
from blogpost.similarity import text_similarity, title_similarity


_AI_TERMS = re.compile(
    r"AI|人工智能|大模型|模型|Agent|智能体|Prompt|AIOps|机器学习|深度学习|推理|RAG|MCP|Token",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|authorization|password|secret)\s*[=:]\s*\S+|\bsk-[A-Za-z0-9_-]{6,}"
)
_DANGEROUS_HTML = re.compile(r"<\s*(script|iframe|object|embed)\b", re.IGNORECASE)


class QualityGate:
    def __init__(
        self,
        min_chinese_chars: int = 800,
        title_threshold: float = 0.76,
        content_threshold: float = 0.68,
    ):
        self.min_chinese_chars = min_chinese_chars
        self.title_threshold = title_threshold
        self.content_threshold = content_threshold

    def check(self, markdown: str, corpus: list[CorpusItem]) -> QualityReport:
        document = parse_markdown(markdown)
        issues: list[QualityIssue] = []
        if not document.title:
            issues.append(QualityIssue("missing_title", "缺少一级标题"))
        if document.heading_count != 1:
            issues.append(QualityIssue("title_count", "必须且只能有一个一级标题"))
        if document.chinese_chars < self.min_chinese_chars:
            issues.append(QualityIssue("too_short", f"正文不足 {self.min_chinese_chars} 个中文字符"))
        if not document.fences_balanced:
            issues.append(QualityIssue("unbalanced_fence", "代码围栏没有闭合"))
        if not _AI_TERMS.search(markdown):
            issues.append(QualityIssue("not_ai", "文章与 AI 技术主题关联不足"))
        if _SECRET.search(markdown):
            issues.append(QualityIssue("secret", "文章疑似包含密钥或口令"))
        if _DANGEROUS_HTML.search(markdown):
            issues.append(QualityIssue("dangerous_html", "文章包含危险 HTML"))

        digest = sha256((markdown.rstrip() + "\n").encode("utf-8")).hexdigest()
        for item in corpus:
            if digest == item.sha256:
                issues.append(QualityIssue("duplicate_hash", "文章与历史内容完全相同"))
                break
            if document.title and title_similarity(document.title, item.title) >= self.title_threshold:
                issues.append(QualityIssue("duplicate_title", f"标题与历史文章《{item.title}》过于相似"))
                break
        if document.body:
            for item in corpus:
                old_body = parse_markdown(item.content).body
                if text_similarity(document.body, old_body) >= self.content_threshold:
                    issues.append(QualityIssue("duplicate_content", f"正文与《{item.title}》过于相似"))
                    break
        return QualityReport(not issues, tuple(issues), 100 if not issues else max(0, 100 - len(issues) * 20))
