from __future__ import annotations

from statistics import median

from blogpost.corpus import CorpusItem
from blogpost.markdown import parse_markdown


def summarize_style(corpus: list[CorpusItem]) -> str:
    if not corpus:
        return "通俗中文技术解释，先提出问题，再分节分析，最后总结。"
    sample = corpus[-30:]
    lengths = [parse_markdown(item.content).chinese_chars for item in sample]
    headings = [item.content.count("\n## ") for item in sample]
    return (
        f"历史文章中位正文约 {int(median(lengths))} 个中文字符，"
        f"通常包含 {int(median(headings))} 个二级章节；"
        "标题偏问题式或观点式，正文用通俗类比解释技术原理，避免营销口吻。"
    )
