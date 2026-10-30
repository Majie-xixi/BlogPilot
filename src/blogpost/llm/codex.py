from __future__ import annotations

import subprocess
import os
import shutil
from pathlib import Path

from blogpost.llm.client import LlmError
from blogpost.config import validate_proxy


def find_codex() -> str | None:
    executable = shutil.which('codex')
    if executable:
        return executable
    if os.name != 'nt' or not os.environ.get('LOCALAPPDATA'):
        return None
    desktop_bin = Path(os.environ['LOCALAPPDATA']) / 'OpenAI' / 'Codex' / 'bin'
    try:
        candidates = [path for path in desktop_bin.glob('*/codex.exe') if path.is_file()]
        return str(max(candidates, key=lambda path: path.stat().st_mtime_ns)) if candidates else None
    except OSError:
        return None


class CodexClient:
    def __init__(self, timeout: float = 600, model: str = '', *, proxy_mode: str = 'environment', proxy_url: str = ''):
        validate_proxy(proxy_mode, proxy_url)
        self.timeout = timeout
        self.model = model.strip()
        self.proxy_mode = proxy_mode
        self.proxy_url = proxy_url

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
            command = [find_codex() or 'codex', 'exec', '--sandbox', 'read-only', '--ephemeral', '--skip-git-repo-check']
            if self.model:
                command.extend(['--model', self.model])
            command.append('-')
            env = None
            if self.proxy_mode != 'environment':
                env = os.environ.copy()
                for key in list(env):
                    if key.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}:
                        del env[key]
                if self.proxy_mode == 'manual':
                    for key in ('HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy'):
                        env[key] = self.proxy_url
                    env['NO_PROXY'] = env['no_proxy'] = ''
                else:
                    env['NO_PROXY'] = env['no_proxy'] = '*'
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise LlmError('未找到 Codex CLI，请检查安装和 PATH') from exc
        except subprocess.TimeoutExpired as exc:
            raise LlmError(f'Codex 调用超时（{self.timeout:g} 秒）；请检查代理、登录状态并在设置中重新测试') from exc
        except OSError as exc:
            raise LlmError('无法启动 Codex CLI') from exc
        if result.returncode != 0:
            raise LlmError('Codex 调用失败，原因未确定；请检查登录状态、额度和代理，再在设置中测试连接')
        content = result.stdout.strip()
        if not content:
            raise LlmError('Codex 未返回内容')
        return content
