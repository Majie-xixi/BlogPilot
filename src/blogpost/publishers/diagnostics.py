from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


def save_diagnostic(directory: Path, html: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    sanitized = re.sub(r"(?i)(authorization|cookie|token|password|secret)(.{0,20})", r"\1=[REDACTED]", html)
    path = directory / f"51cto-{datetime.now():%Y%m%d-%H%M%S}.html"
    path.write_text(sanitized[:500_000], encoding="utf-8")
    return path
