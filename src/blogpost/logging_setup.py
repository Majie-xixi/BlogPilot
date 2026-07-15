from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re


_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
)


def redact(value: str) -> str:
    result = value
    for pattern in _PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = redact(message)
        record.args = ()
        return True


def configure_logging(path: Path, verbose: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for handler in (
        RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(),
    ):
        handler.addFilter(RedactingFilter())
        handler.setFormatter(formatter)
        root.addHandler(handler)
