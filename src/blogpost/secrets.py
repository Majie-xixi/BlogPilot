from __future__ import annotations

from dataclasses import dataclass, field
import base64
import ctypes
from ctypes import wintypes
import os
import re
from pathlib import Path
from typing import Protocol


SERVICE_NAME = "BlogPostPublisher"
API_KEY_NAME = "model-api-key"


class SecretStore(Protocol):
    def get_api_key(self, connection_id: str = "legacy-api") -> str | None: ...
    def set_api_key(self, value: str, connection_id: str = "legacy-api") -> None: ...
    def delete_api_key(self, connection_id: str = "legacy-api") -> None: ...


@dataclass
class MemorySecretStore:
    values: dict[str, str] = field(default_factory=dict)

    def get_api_key(self, connection_id: str = "legacy-api") -> str | None:
        return self.values.get(connection_id)

    def set_api_key(self, value: str, connection_id: str = "legacy-api") -> None:
        self.values[connection_id] = value

    def delete_api_key(self, connection_id: str = "legacy-api") -> None:
        self.values.pop(connection_id, None)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from_bytes(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _protect(value: bytes) -> bytes:
    source, keepalive = _blob_from_bytes(value)
    destination = _DataBlob()
    result = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)
    )
    _ = keepalive
    if not result:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _unprotect(value: bytes) -> bytes:
    source, keepalive = _blob_from_bytes(value)
    destination = _DataBlob()
    result = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)
    )
    _ = keepalive
    if not result:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


class DpapiSecretStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _path_for(self, connection_id: str) -> Path:
        if connection_id == "legacy-api":
            return self.path
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", connection_id):
            raise ValueError("invalid connection id")
        return self.path.parent / "model-keys" / f"{connection_id}.bin"

    def get_api_key(self, connection_id: str = "legacy-api") -> str | None:
        env_value = os.environ.get("BLOGPOST_API_KEY") if connection_id == "legacy-api" else None
        if env_value:
            return env_value
        path = self._path_for(connection_id)
        if not path.exists():
            return None
        encrypted = base64.b64decode(path.read_bytes())
        return _unprotect(encrypted).decode("utf-8")

    def set_api_key(self, value: str, connection_id: str = "legacy-api") -> None:
        path = self._path_for(connection_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = base64.b64encode(_protect(value.encode("utf-8")))
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        temp.replace(path)

    def delete_api_key(self, connection_id: str = "legacy-api") -> None:
        self._path_for(connection_id).unlink(missing_ok=True)
