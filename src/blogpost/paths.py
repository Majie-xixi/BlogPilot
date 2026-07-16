from __future__ import annotations

import os
from pathlib import Path
import sys


DATA_DIR_ENV = "BLOGPILOT_DATA_DIR"
DATA_DIR_MARKER = "blogpilot-data-dir.txt"


def _data_dir_marker() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / DATA_DIR_MARKER
    return Path(__file__).resolve().parents[2] / DATA_DIR_MARKER


def legacy_app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "BlogPostPublisher"
    return Path.home() / ".blogpost-publisher"


def app_data_dir() -> Path:
    configured = os.environ.get(DATA_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    marker = _data_dir_marker()
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = marker.parent / path
            return path.resolve()
    return legacy_app_data_dir()


def config_path() -> Path:
    return app_data_dir() / "config.json"


def database_path() -> Path:
    return app_data_dir() / "blogpost.db"


def log_path() -> Path:
    return app_data_dir() / "logs" / "application.log"


def browser_profile_dir() -> Path:
    return app_data_dir() / "chrome-profile"
