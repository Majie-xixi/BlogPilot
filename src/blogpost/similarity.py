from __future__ import annotations

from collections import Counter
from math import sqrt
import re
import unicodedata


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", value)


def _ngrams(value: str, size: int = 2) -> Counter[str]:
    normalized = normalize_text(value)
    if len(normalized) <= size:
        return Counter({normalized: 1}) if normalized else Counter()
    return Counter(normalized[index : index + size] for index in range(len(normalized) - size + 1))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[key] * right[key] for key in common)
    magnitude = sqrt(sum(value * value for value in left.values())) * sqrt(
        sum(value * value for value in right.values())
    )
    return dot / magnitude if magnitude else 0.0


def title_similarity(left: str, right: str) -> float:
    if normalize_text(left) == normalize_text(right) and normalize_text(left):
        return 1.0
    return _cosine(_ngrams(left), _ngrams(right))


def text_similarity(left: str, right: str) -> float:
    return _cosine(_ngrams(left, 2), _ngrams(right, 2))
