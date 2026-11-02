from __future__ import annotations

from importlib.resources import files
import re
from collections.abc import Mapping

_CAPTURABLE_TERM = re.compile(r"^[\w\u4e00-\u9fff-]{1,8}$")


def load_builtin_words() -> dict[str, str]:
    """读取随程序发布的敏感词基线文件。"""
    text = (
        files("blogpost.data")
        .joinpath("sensitive_words.txt")
        .read_text(encoding="utf-8")
    )
    words: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, _, replacement = line.partition("|")
        term = term.strip()
        if not term:
            continue
        words.setdefault(term, replacement.strip())
    return words


def merge_sensitive_words(*layers: Mapping[str, str | None]) -> dict[str, str]:
    """按优先级合并多层词库（高优先级在前）。

    是否命中取并集：任一层标记的词都生效；替换建议取优先级最高层的
    非空值，高层没有建议（例如平台只告知了词）时不会遮蔽低层已有的建议。
    """
    merged: dict[str, str] = {}
    for layer in layers:
        for term, replacement in layer.items():
            term = str(term).strip()
            if not term or merged.get(term):
                continue
            merged[term] = str(replacement or "").strip()
    return merged


def effective_sensitive_words(local_words: Mapping[str, str | None]) -> dict[str, str]:
    """本地词库（手动/自动捕获）与内置基线合并后的生效词表。"""
    return merge_sensitive_words(local_words, load_builtin_words())


def clean_captured_term(term: str) -> str | None:
    """清洗平台审核提示中提取的词；句子或过长文本不入库，防止污染词库。"""
    term = term.strip().strip("“”‘’\"'。！？，、；:")
    if _CAPTURABLE_TERM.match(term):
        return term
    return None


def scan_sensitive_hits(text: str, words: Mapping[str, str]) -> list[str]:
    """返回文本中命中的敏感词，用于重发前的最后拦截。"""
    return [term for term in words if term and term in text]
