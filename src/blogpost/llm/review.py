from __future__ import annotations

import json

from blogpost.domain import QualityIssue, QualityReport
from blogpost.llm.generation import CompletionClient, _strip_fence


class ModelReviewer:
    def __init__(self, client: CompletionClient):
        self.client = client

    def review(self, markdown: str) -> QualityReport:
        prompt = f"""审查下面 AI 技术博客。检查技术相关性、逻辑完整性、伪原创痕迹、虚构亲历、无法支持的数字和自相矛盾。
同时检查社区发布适配性：如果存在容易触发社区审核、且能在不损失技术准确性的前提下改为中性专业表达的敏感、煽动或行动指令式措辞，必须返回 hard=true、code="platform_sensitive_wording" 的问题并给出改写建议。
只返回 JSON：{{"passed":true,"score":0-100,"issues":[{{"code":"...","message":"...","hard":true}}]}}

文章：
{markdown}"""
        try:
            raw = self.client.complete([{"role": "user", "content": prompt}], temperature=0.1, json_mode=True)
            data = json.loads(_strip_fence(raw))
            issues = tuple(
                QualityIssue(
                    str(item.get("code", "review_issue")),
                    str(item.get("message", "模型复核发现问题")),
                    bool(item.get("hard", True)),
                )
                for item in data.get("issues", [])
            )
            passed = bool(data.get("passed", False)) and not any(issue.hard for issue in issues)
            return QualityReport(passed, issues, int(data.get("score", 0)))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return QualityReport(
                False,
                (QualityIssue("review_parse_error", "模型复核结果无法解析"),),
                0,
            )
