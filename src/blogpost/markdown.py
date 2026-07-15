from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(slots=True, frozen=True)
class MarkdownDocument:
    title: str
    body: str
    chinese_chars: int
    fences_balanced: bool
    heading_count: int


def _outside_fence_h1(lines: list[str]) -> tuple[list[tuple[int, str]], bool]:
    headings: list[tuple[int, str]] = []
    fence_char: str | None = None
    for index, line in enumerate(lines):
        fence = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            marker = fence.group(1)[0]
            if fence_char is None:
                fence_char = marker
            elif fence_char == marker:
                fence_char = None
            continue
        if fence_char is None:
            heading = re.match(r"^#\s+(.+?)\s*$", line)
            if heading:
                headings.append((index, heading.group(1).strip()))
    return headings, fence_char is None


def parse_markdown(content: str) -> MarkdownDocument:
    normalized = content.replace("\r\n", "\n").strip()
    lines = normalized.splitlines()
    headings, fences_balanced = _outside_fence_h1(lines)
    title = headings[0][1] if headings else ""
    if headings:
        body_lines = lines[: headings[0][0]] + lines[headings[0][0] + 1 :]
        body = "\n".join(body_lines).strip()
    else:
        body = normalized
    chinese_chars = len(re.findall(r"[\u3400-\u9fff]", body))
    return MarkdownDocument(
        title=title,
        body=body,
        chinese_chars=chinese_chars,
        fences_balanced=fences_balanced,
        heading_count=len(headings),
    )


def normalize_single_h1(content: str, fallback_title: str) -> str:
    """Guarantee one document-level H1 without touching comments inside code fences."""
    normalized = content.replace("\r\n", "\n").strip()
    lines = normalized.splitlines()
    headings, _ = _outside_fence_h1(lines)
    if headings:
        first_index = headings[0][0]
        lines[first_index] = f"# {fallback_title.strip()}"
        for index, heading in headings[1:]:
            lines[index] = f"## {heading}"
    else:
        first_content = next((index for index, line in enumerate(lines) if line.strip()), None)
        if first_content is not None and lines[first_content].strip() == fallback_title.strip():
            lines[first_content] = f"# {fallback_title.strip()}"
        else:
            lines = [f"# {fallback_title.strip()}", "", *lines]
    return "\n".join(lines).strip()


def safe_filename(value: str, max_length: int = 80) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"[\s_-]+", "-", value).strip(" .-")
    return (value[:max_length].rstrip(" .-") or "untitled")
