from __future__ import annotations

import itertools
from typing import Any

from blogpost.browser.websocket import WebSocketClient


class CdpError(RuntimeError):
    pass


class CdpSession:
    def __init__(self, websocket_url: str, timeout: float = 20):
        self.websocket = WebSocketClient(websocket_url, timeout)
        self._ids = itertools.count(1)

    def __enter__(self) -> "CdpSession":
        self.websocket.connect()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.websocket.close()

    def command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        identifier = next(self._ids)
        self.websocket.send_json({"id": identifier, "method": method, "params": params or {}})
        while True:
            message = self.websocket.receive_json()
            if message.get("id") != identifier:
                continue
            if "error" in message:
                raise CdpError(str(message["error"]))
            return message.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise CdpError(remote.get("description", "JavaScript evaluation failed"))
        return remote.get("value")
