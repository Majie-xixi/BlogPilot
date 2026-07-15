from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_CHROME_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
)


def find_chrome() -> Path:
    for path in _CHROME_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("未找到 Google Chrome")


class ChromeController:
    def __init__(self, executable: Path, profile_dir: Path):
        self.executable = Path(executable)
        self.profile_dir = Path(profile_dir)
        self.port: int | None = None
        self.process: subprocess.Popen | None = None

    def build_launch_args(self, port: int, url: str) -> list[str]:
        return [
            str(self.executable),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]

    def start(self, url: str, timeout: float = 15, port: int = 9229) -> int:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        try:
            self.version()
            self.open_tab(url)
            return self.port
        except (URLError, ConnectionError, OSError):
            pass
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            self.build_launch_args(self.port, url),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.version()
                return self.port
            except (URLError, ConnectionError, OSError):
                time.sleep(0.2)
        raise TimeoutError("Chrome 调试端口启动超时")

    def version(self) -> dict:
        return self._json_request("/json/version")

    def list_targets(self) -> list[dict]:
        return self._json_request("/json/list")

    def open_tab(self, url: str) -> dict:
        return self._json_request(f"/json/new?{quote(url, safe=':/?=&')}", method="PUT")

    def wait_for_target(self, url_prefix: str, timeout: float = 15) -> dict:
        """Wait for Chrome to expose a page target for a newly opened URL."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for target in self.list_targets():
                if target.get("type") == "page" and str(target.get("url", "")).startswith(url_prefix):
                    return target
            time.sleep(0.2)
        raise TimeoutError(f"Chrome 页面打开超时：{url_prefix}")

    def _json_request(self, path: str, method: str = "GET") -> dict:
        if self.port is None:
            raise RuntimeError("Chrome is not started")
        request = Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
