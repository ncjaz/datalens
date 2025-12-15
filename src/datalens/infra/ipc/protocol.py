from __future__ import annotations

import json
import secrets
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

DEFAULT_MAX_HEADER_BYTES = 1024 * 1024
DEFAULT_MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
PROTOCOL_VERSION = 1


class FrameDecodeError(ValueError):
    pass


def new_request_id() -> str:
    return uuid.uuid4().hex


def new_endpoint_name(prefix: str = "datalens") -> str:
    """
    Return a short, ASCII-only name suitable for `QLocalServer.listen(...)`.

    Keep names short to avoid platform-specific length limits (Unix domain socket
    path constraints, named pipe naming quirks).
    """
    return f"{prefix}-{secrets.token_hex(8)}"


@dataclass(frozen=True, slots=True)
class IpcHello:
    token: str
    peer_name: str | None = None
    protocol_version: int = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class EventMessage:
    topic: str
    data: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RpcRequest:
    request_id: str
    method: str
    params: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RpcResponse:
    request_id: str
    ok: bool
    result: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def encode_frame(header: dict[str, Any], payload: bytes = b"") -> bytes:
    header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return struct.pack("!II", len(header_bytes), len(payload)) + header_bytes + payload


def decode_frames_from_buffer(
    buffer: bytearray,
    *,
    max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> Iterable[tuple[dict[str, Any], bytes]]:
    while True:
        if len(buffer) < 8:
            return

        header_len, payload_len = struct.unpack("!II", buffer[:8])
        if header_len > max_header_bytes:
            raise FrameDecodeError(f"Header too large: {header_len} bytes")
        if payload_len > max_payload_bytes:
            raise FrameDecodeError(f"Payload too large: {payload_len} bytes")

        total_len = 8 + header_len + payload_len
        if len(buffer) < total_len:
            return

        header_bytes = bytes(buffer[8 : 8 + header_len])
        payload = bytes(buffer[8 + header_len : total_len])
        del buffer[:total_len]

        try:
            header = json.loads(header_bytes.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            raise FrameDecodeError("Invalid JSON header") from exc

        if not isinstance(header, dict):
            raise FrameDecodeError("Frame header must be a JSON object")

        yield header, payload

