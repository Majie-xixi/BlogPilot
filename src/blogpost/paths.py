from __future__ import annotations

import os
from pathlib import Path
import sys


DATA_DIR_ENV = "BLOGPILOT_DATA_DIR"
DATA_DIR_MARKER = "blogpilot-data-dir.txt"
REGISTRY_KEY = r"Software\BlogPilot"
REGISTRY_VALUE = "DataDirectory"
DATA_SUBDIRECTORIES = (
    "articles",
    "logs",
    "diagnostics",
    "chrome-profiles",
    "backups",
)


def _data_dir_marker() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / DATA_DIR_MARKER
    return Path(__file__).resolve().parents[2] / DATA_DIR_MARKER


def legacy_app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "BlogPostPublisher"
    return Path.home() / ".blogpost-publisher"


def _registry_data_dir() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, REGISTRY_VALUE)
    except OSError:
        return None
    value = str(value).strip()
    return Path(value).expanduser().resolve() if value else None


def _write_registry_data_dir(path: Path) -> None:
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, str(path))
        return
    marker = _data_dir_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(path), encoding="utf-8")


def configured_data_dir() -> Path | None:
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
    return _registry_data_dir()


def initialize_data_dir(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (resolved / name).mkdir(parents=True, exist_ok=True)
    return resolved


def save_data_dir(path: Path) -> Path:
    resolved = initialize_data_dir(path)
    _write_registry_data_dir(resolved)
    return resolved


def app_data_dir() -> Path:
    return configured_data_dir() or legacy_app_data_dir()


def config_path() -> Path:
    return app_data_dir() / "config.json"


def database_path() -> Path:
    return app_data_dir() / "blogpost.db"


def log_path() -> Path:
    return app_data_dir() / "logs" / "application.log"


def browser_profile_dir(account_id: str = "default") -> Path:
    safe_id = "".join(char for char in account_id if char.isalnum() or char in "-_") or "default"
    if safe_id == "default":
        # Preserve the existing signed-in session during the multi-account migration.
        return app_data_dir() / "chrome-profile"
    return app_data_dir() / "chrome-profiles" / safe_id
