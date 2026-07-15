from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
from urllib.parse import urlsplit


class WebSocketError(RuntimeError):
    pass


def encode_text_frame(text: str, mask_key: bytes | None = None) -> bytes:
    return _encode_frame(0x1, text.encode("utf-8"), mask_key)


def _encode_frame(opcode: int, payload: bytes, mask_key: bytes | None = None) -> bytes:
    key = mask_key or os.urandom(4)
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes((first, 0x80 | length))
    elif length <= 0xFFFF:
        header = bytes((first, 0x80 | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 0x80 | 127)) + struct.pack("!Q", length)
    masked = bytes(value ^ key[index % 4] for index, value in enumerate(payload))
    return header + key + masked


class WebSocketClient:
    def __init__(self, url: str, timeout: float = 20):
        parsed = urlsplit(url)
        if parsed.scheme != "ws":
            raise WebSocketError("only local ws:// endpoints are supported")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.timeout = timeout
        self.socket: socket.socket | None = None
        self._buffer = b""

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Origin: http://{self.host}:{self.port}\r\n\r\n"
        ).encode("ascii")
        sock.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise WebSocketError("websocket handshake closed")
            response += chunk
        header, self._buffer = response.split(b"\r\n\r\n", 1)
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise WebSocketError(f"websocket handshake failed: {header[:160]!r}")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        )
        if expected.lower() not in header.lower():
            raise WebSocketError("invalid websocket accept key")
        self.socket = sock

    def close(self) -> None:
        if self.socket is not None:
            try:
                self.socket.sendall(_encode_frame(0x8, b""))
            except OSError:
                pass
            self.socket.close()
            self.socket = None

    def send_json(self, data: dict) -> None:
        if self.socket is None:
            raise WebSocketError("websocket is not connected")
        self.socket.sendall(encode_text_frame(json.dumps(data, ensure_ascii=False)))

    def receive_json(self) -> dict:
        fragments = bytearray()
        while True:
            opcode, payload, final = self._receive_frame()
            if opcode == 0x8:
                raise WebSocketError("websocket closed")
            if opcode == 0x9:
                if self.socket is not None:
                    self.socket.sendall(_encode_frame(0xA, payload))
                continue
            if opcode in (0x1, 0x0):
                fragments.extend(payload)
                if final:
                    return json.loads(fragments.decode("utf-8"))

    def _receive_frame(self) -> tuple[int, bytes, bool]:
        header = self._read_exact(2)
        final = bool(header[0] & 0x80)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        key = self._read_exact(4) if masked else None
        payload = self._read_exact(length)
        if key:
            payload = bytes(value ^ key[index % 4] for index, value in enumerate(payload))
        return opcode, payload, final

    def _read_exact(self, length: int) -> bytes:
        if self.socket is None:
            raise WebSocketError("websocket is not connected")
        while len(self._buffer) < length:
            chunk = self.socket.recv(max(4096, length - len(self._buffer)))
            if not chunk:
                raise WebSocketError("websocket closed during frame")
            self._buffer += chunk
        result, self._buffer = self._buffer[:length], self._buffer[length:]
        return result
