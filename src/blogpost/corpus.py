from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from blogpost.markdown import parse_markdown


@dataclass(slots=True, frozen=True)
class CorpusItem:
    path: Path
    title: str
    content: str
    sha256: str
    historical: bool = True


class CorpusIndexer:
    def __init__(self, history_dir: Path, generated_dir: Path):
        self.history_dir = Path(history_dir)
        self.generated_dir = Path(generated_dir)

    def scan_history(self) -> list[CorpusItem]:
        if not self.history_dir.exists():
            return []
        items: list[CorpusItem] = []
        for path in sorted(self.history_dir.glob("*.md"), key=lambda item: item.name):
            if self._inside_generated(path):
                continue
            content = path.read_text(encoding="utf-8")
            document = parse_markdown(content)
            if not document.title:
                continue
            items.append(
                CorpusItem(
                    path=path,
                    title=document.title,
                    content=content,
                    sha256=sha256(content.encode("utf-8")).hexdigest(),
                )
            )
        return items

    def scan_generated(self) -> list[CorpusItem]:
        if not self.generated_dir.exists():
            return []
        items = []
        for path in sorted(self.generated_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            document = parse_markdown(content)
            if document.title:
                items.append(
                    CorpusItem(
                        path,
                        document.title,
                        content,
                        sha256(content.encode("utf-8")).hexdigest(),
                        False,
                    )
                )
        return items

    def _inside_generated(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.generated_dir.resolve())
            return True
        except ValueError:
            return False
