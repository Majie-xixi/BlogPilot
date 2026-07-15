from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LlmError(RuntimeError):
    pass


class LlmAuthError(LlmError):
    pass


class LlmRateLimitError(LlmError):
    pass


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _urllib_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        *,
        timeout: float = 90,
        max_retries: int = 2,
        transport: Transport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport or _urllib_transport

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BlogPostPublisher/0.1",
        }
        for attempt in range(self.max_retries + 1):
            try:
                data = self.transport(
                    f"{self.base_url}/chat/completions",
                    headers,
                    payload,
                    self.timeout,
                )
                return str(data["choices"][0]["message"]["content"]).strip()
            except HTTPError as exc:
                if exc.code in (401, 403):
                    raise LlmAuthError("大模型 API 鉴权失败，请检查密钥") from exc
                if exc.code == 429:
                    if attempt >= self.max_retries:
                        raise LlmRateLimitError("大模型 API 请求过于频繁") from exc
                elif 500 <= exc.code < 600 and attempt < self.max_retries:
                    pass
                else:
                    raise LlmError(f"大模型 API 返回 HTTP {exc.code}") from exc
            except (URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if attempt >= self.max_retries:
                    raise LlmError(f"大模型 API 响应失败：{exc}") from exc
            time.sleep(min(2**attempt, 4))
        raise LlmError("大模型 API 调用失败")
