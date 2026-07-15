from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
import os
import tempfile

from blogpost.markdown import safe_filename


@dataclass(slots=True, frozen=True)
class StoredArticle:
    path: Path
    sha256: str


class ArticleStore:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def save(self, title: str, content: str, day: date | None = None) -> StoredArticle:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prefix = (day or date.today()).isoformat()
        stem = f"{prefix}-{safe_filename(title)}"
        target = self.output_dir / f"{stem}.md"
        counter = 2
        while target.exists():
            target = self.output_dir / f"{stem}-{counter}.md"
            counter += 1
        handle, temp_name = tempfile.mkstemp(prefix=".article-", suffix=".tmp", dir=self.output_dir)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content.rstrip() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            Path(temp_name).replace(target)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
        digest = sha256((content.rstrip() + "\n").encode("utf-8")).hexdigest()
        return StoredArticle(target, digest)
