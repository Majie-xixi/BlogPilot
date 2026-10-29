from __future__ import annotations

import subprocess

from blogpost.llm.client import LlmError


class CodexClient:
    def __init__(self, timeout: float = 600):
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        # Codex does not expose the chat-completions temperature parameter.
        instruction = "请直接完成以下内容生成任务，仅输出结果，不要使用工具或修改文件。"
        if json_mode:
            instruction += "结果必须是有效 JSON，不要使用代码围栏。"
        prompt = instruction + "\n\n" + "\n\n".join(
            f"[{message['role']}]\n{message['content']}" for message in messages
        )
        try:
            result = subprocess.run(
                ['codex', 'exec', '--sandbox', 'read-only', '--ephemeral', '--skip-git-repo-check', '-'],
                input=prompt,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                check=False,
            )
        except FileNotFoundError as exc:
            raise LlmError('未找到 Codex CLI，请检查安装和 PATH') from exc
        except subprocess.TimeoutExpired as exc:
            raise LlmError('Codex 调用超时') from exc
        except OSError as exc:
            raise LlmError('无法启动 Codex CLI') from exc
        if result.returncode != 0:
            raise LlmError('Codex 调用失败，请检查登录状态、额度和网络')
        content = result.stdout.strip()
        if not content:
            raise LlmError('Codex 未返回内容')
        return content
