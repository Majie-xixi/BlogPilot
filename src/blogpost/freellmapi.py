"""Install and discover the official Windows desktop gateway on loopback."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener, urlopen

VERSION = '0.16.12'
INSTALLER_URL = f'https://github.com/tashfeenahmed/freellmapi/releases/download/v{VERSION}/FreeLLMAPI-Setup-{VERSION}.exe'
INSTALLER_SHA256 = 'd953c4577991eb217f80dd4bd85b8948e9dd46a4163c2ec22a6007938b882775'


class FreeLLMAPIError(RuntimeError):
    pass


class FreeLLMAPIService:
    def installed_path(self) -> Path:
        return Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'freellmapi-desktop' / 'FreeLLMAPI.exe'

    def is_installed(self) -> bool:
        return bool(os.environ.get('LOCALAPPDATA')) and self.installed_path().is_file()

    def _process_path(self, pid: int) -> Path | None:
        if os.name != 'nt':
            return None
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            return Path(buffer.value) if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        finally:
            kernel.CloseHandle(handle)

    def _listener_ports(self) -> list[int]:
        if os.name != 'nt' or not self.is_installed():
            return []
        result = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True,
                                timeout=10, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        ports = []
        expected = os.path.normcase(str(self.installed_path().resolve()))
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 5 or fields[0] != 'TCP' or fields[3] != 'LISTENING':
                continue
            host, _, port = fields[1].rpartition(':')
            if host != '127.0.0.1' or not port.isdigit() or not 31415 <= int(port) < 31465:
                continue
            process = self._process_path(int(fields[4]))
            if process and os.path.normcase(str(process.resolve())) == expected:
                ports.append(int(port))
        return ports

    def _request(self, port: int, path: str, data=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        payload = None if data is None else json.dumps(data).encode('utf-8')
        # Bypass system proxies for secrets sent to loopback.
        opener = build_opener(ProxyHandler({}))
        with opener.open(Request(f'http://127.0.0.1:{port}{path}', data=payload, headers=headers), timeout=5) as response:
            return json.load(response)

    def discover(self) -> tuple[str, str]:
        for port in self._listener_ports():
            try:
                if not self._request(port, '/api/auth/status').get('desktop'):
                    continue
                token = self._request(port, '/api/auth/desktop-session', {})['token']
                key = self._request(port, '/api/settings/api-key', token=token)['apiKey']
                if not isinstance(key, str) or not key.strip():
                    continue
                return f'http://127.0.0.1:{port}/v1', key
            except (OSError, ValueError, KeyError, TypeError):
                continue
        raise FreeLLMAPIError('未发现可用的 FreeLLMAPI 桌面服务，请检查服务是否已启动。')

    def install(self, progress=lambda _message: None) -> None:
        if os.name != 'nt':
            raise FreeLLMAPIError('自动安装仅支持 Windows。')
        progress(f'正在下载 FreeLLMAPI {VERSION}…')
        with tempfile.TemporaryDirectory(prefix='blogpilot-freellmapi-') as directory:
            installer = Path(directory) / 'setup.exe'
            digest = hashlib.sha256()
            try:
                with urlopen(INSTALLER_URL, timeout=60) as response, installer.open('wb') as target:
                    while chunk := response.read(1024 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
                if digest.hexdigest() != INSTALLER_SHA256:
                    raise FreeLLMAPIError('安装包校验失败，已停止安装。')
                progress('校验通过，正在安装…')
                result = subprocess.run([str(installer), '/S', '/currentuser'], timeout=180,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
                if result.returncode != 0 or not self.is_installed():
                    raise FreeLLMAPIError('安装未完成，请检查系统权限和安装程序。')
            except FreeLLMAPIError:
                raise
            except (OSError, TimeoutError, subprocess.SubprocessError) as exc:
                raise FreeLLMAPIError('下载或安装失败，请检查网络和系统权限。') from exc

    def prepare(self, install_if_missing: bool, progress=lambda _message: None) -> tuple[str, str]:
        new_install = not self.is_installed()
        if new_install:
            if not install_if_missing:
                raise FreeLLMAPIError('尚未安装 FreeLLMAPI。')
            self.install(progress)
        try:
            base, key = self.discover()
        except FreeLLMAPIError:
            progress('正在启动 FreeLLMAPI…')
            try:
                subprocess.Popen([str(self.installed_path())], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError as exc:
                raise FreeLLMAPIError('无法启动 FreeLLMAPI。') from exc
            deadline = time.monotonic() + 35
            while True:
                try:
                    base, key = self.discover()
                    break
                except FreeLLMAPIError:
                    if time.monotonic() >= deadline:
                        raise FreeLLMAPIError('服务启动超时，请检查 FreeLLMAPI 日志。')
                    time.sleep(1)
        if new_install:
            port = int(base.split(':')[-1].split('/')[0])
            try:
                token = self._request(port, '/api/auth/desktop-session', {})['token']
                providers = self._request(port, '/api/keys/providers', token=token)['providers']
                if not any(p.get('kind') == 'chat' and p.get('enabledKeyCount', 0) for p in providers):
                    for platform in ('ovh', 'kilo'):
                        self._request(port, '/api/keys', {'platform': platform, 'label': 'BlogPilot 免密'}, token)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise FreeLLMAPIError('服务已启动，但免密供应商配置失败，请打开管理页检查。') from exc
        return base, key
