from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_CHROME_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
)

_EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
)


@dataclass(frozen=True, slots=True)
class BrowserInstallation:
    name: str
    executable: Path


def find_google_chrome() -> Path:
    for path in _CHROME_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("未找到 Google Chrome")


def find_supported_browser() -> BrowserInstallation:
    for name, paths in (("Chrome", _CHROME_PATHS), ("Edge", _EDGE_PATHS)):
        for path in paths:
            if path.exists():
                return BrowserInstallation(name, path)
    raise FileNotFoundError("未找到 Google Chrome 或 Microsoft Edge")


def find_chrome() -> Path:
    """Backward-compatible alias for older call sites."""
    return find_supported_browser().executable


class ChromeController:
    def __init__(
        self,
        executable: Path,
        profile_dir: Path,
        default_port: int = 9229,
        browser_name: str = "Chrome",
    ):
        self.executable = Path(executable)
        self.profile_dir = Path(profile_dir)
        self.default_port = default_port
        self.browser_name = browser_name
        self.port: int | None = None
        self.process: subprocess.Popen | None = None

    def build_launch_args(self, port: int, url: str) -> list[str]:
        return [
            str(self.executable),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile_dir}",
            # This profile exists only for 51CTO automation. Do not let it
            # trigger component/model downloads or unrelated background services.
            "--disable-component-update",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-features=OptimizationHints,OptimizationGuideModelDownloading,ModelExecution,Compose,AutofillPredictionImprovements",
            "--disable-domain-reliability",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-popup-blocking",
            "--no-pings",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]

    def find_available_port(self, preferred_port: int, attempts: int = 20) -> int:
        upper_bound = min(preferred_port + attempts, 65536)
        for candidate in range(preferred_port, upper_bound):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind(("127.0.0.1", candidate))
                except OSError:
                    continue
            return candidate
        raise OSError(f"没有可用的 {self.browser_name} 调试端口")

    def start(self, url: str, timeout: float = 15, port: int | None = None) -> int:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if self.process is not None and self.process.poll() is None and self.port is not None:
            try:
                self.version()
                self.open_tab(url)
                return self.port
            except (URLError, ConnectionError, OSError):
                pass
        preferred_port = self.default_port if port is None else port
        self.port = self.find_available_port(preferred_port)
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
        raise TimeoutError(f"{self.browser_name} 调试端口启动超时")

    def version(self) -> dict:
        return self._json_request("/json/version")

    def list_targets(self) -> list[dict]:
        return self._json_request("/json/list")

    def open_tab(self, url: str) -> dict:
        return self._json_request(f"/json/new?{quote(url, safe=':/?=&')}", method="PUT")

    def wait_for_target(self, url_prefix: str, timeout: float = 15) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for target in self.list_targets():
                if target.get("type") == "page" and str(target.get("url", "")).startswith(
                    url_prefix
                ):
                    return target
            time.sleep(0.2)
        raise TimeoutError(f"{self.browser_name} 页面打开超时：{url_prefix}")

    def _json_request(self, path: str, method: str = "GET") -> dict:
        if self.port is None:
            raise RuntimeError(f"{self.browser_name} is not started")
        request = Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
