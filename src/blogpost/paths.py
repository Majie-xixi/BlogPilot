from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "BlogPostPublisher"
    return Path.home() / ".blogpost-publisher"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def database_path() -> Path:
    return app_data_dir() / "blogpost.db"


def log_path() -> Path:
    return app_data_dir() / "logs" / "application.log"


def browser_profile_dir() -> Path:
    return app_data_dir() / "chrome-profile"
