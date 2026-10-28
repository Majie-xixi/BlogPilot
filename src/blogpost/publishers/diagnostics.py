from __future__ import annotations

from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re

from blogpost.logging_setup import redact


_SECRET_NAMES = r"(?:authorization|cookie|password|secret|(?:access|refresh|csrf|auth|session)[_-]?token|token|api[_-]?key)"
_QUOTED_SECRET = re.compile(
    rf'''(["']?{_SECRET_NAMES}["']?\s*[:=]\s*)(["'])(.*?)\2''',
    re.IGNORECASE | re.DOTALL,
)
_SAFE_TAGS = set(
    "html head title body div span p section article main header footer nav aside "
    "h1 h2 h3 h4 h5 h6 ul ol li table thead tbody tr th td label input textarea "
    "button select option a pre code b strong i em br hr small dl dt dd".split()
)
_SAFE_ATTRIBUTES = set(
    "id class type name placeholder readonly disabled checked selected role "
    "aria-label aria-expanded title colspan rowspan".split()
)
_BLOCKED_CONTENT = {"script", "style", "iframe", "object", "svg", "math", "template"}


def _redact_text(value: str) -> str:
    value = _QUOTED_SECRET.sub(lambda match: match[1] + match[2] + "[REDACTED]" + match[2], value)
    return redact(value)


class _DiagnosticSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_tag: str | None = None
        self.blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.blocked_tag:
            if tag == self.blocked_tag:
                self.blocked_depth += 1
            return
        if tag in _BLOCKED_CONTENT:
            self.blocked_tag, self.blocked_depth = tag, 1
            return
        attributes = dict(attrs)
        if tag not in _SAFE_TAGS or (
            tag == "input" and attributes.get("type", "").lower() in {"hidden", "password"}
        ):
            return
        safe = []
        for key, value in attrs:
            if key in _SAFE_ATTRIBUTES:
                safe.append(key if value is None else f'{key}="{escape(_redact_text(value), quote=True)}"')
        if "value" in attributes:
            safe.append('value="[REDACTED]"')
        if tag in {"input", "button", "textarea", "select"} and "disabled" not in attributes:
            safe.append("disabled")
        self.parts.append(f"<{tag}{' ' if safe else ''}{' '.join(safe)}>")

    def handle_endtag(self, tag):
        if self.blocked_tag:
            if tag == self.blocked_tag:
                self.blocked_depth -= 1
                if not self.blocked_depth:
                    self.blocked_tag = None
            return
        if tag in _SAFE_TAGS and tag not in {"input", "br", "hr"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked_tag:
            self.parts.append(escape(_redact_text(data)))


def sanitize_diagnostic_html(html: str) -> str:
    parser = _DiagnosticSanitizer()
    parser.feed(html)
    parser.close()
    return '<meta charset="utf-8">\n' + "".join(parser.parts)


def save_diagnostic(directory: Path, html: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_diagnostic_html(html)
    path = directory / f"51cto-{datetime.now():%Y%m%d-%H%M%S}.html"
    path.write_text(sanitized[:500_000], encoding="utf-8")
    return path
