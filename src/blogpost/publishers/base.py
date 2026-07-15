from __future__ import annotations

from typing import Protocol

from blogpost.domain import Article, PublishResult


class Publisher(Protocol):
    def publish(self, article: Article, category: str, dry_run: bool) -> PublishResult: ...
