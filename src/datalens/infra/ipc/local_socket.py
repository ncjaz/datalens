from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from datalens.infra.ipc.protocol import FrameDecodeError, decode_frames_from_buffer, encode_frame

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocalSocketConfig:
    server_name: str
    token: str | None = None
    handshake_timeout_ms: int = 5_000


class FramedLocalSocket(QObject):
    frame_received = Signal(object, object)  # header: dict[str, Any], payload: bytes
    disconnected = Signal()
    error = Signal(str)

    def __init__(
        self,
        socket: QLocalSocket,
        *,
        max_header_bytes: int = 1024 * 1024,
        max_payload_bytes: int = 128 * 1024 * 1024,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._socket = socket
        self._buffer = bytearray()
        self._max_header_bytes = max_header_bytes
        self._max_payload_bytes = max_payload_bytes

        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self.disconnected.emit)
        self._socket.errorOccurred.connect(self._on_error)

    @property
    def socket(self) -> QLocalSocket:
        return self._socket

    def send(self, header: dict[str, Any], payload: bytes = b"") -> None:
        data = encode_frame(header, payload)
        self._socket.write(data)
        self._socket.flush()

    def close(self) -> None:
        self._socket.disconnectFromServer()

    def _on_error(self, error) -> None:  # pragma: no cover - Qt enum typing varies
        self.error.emit(str(error))

    def _on_ready_read(self) -> None:
        data = bytes(self._socket.readAll())
        if not data:
            return

        self._buffer.extend(data)
        try:
            for header, payload in decode_frames_from_buffer(
                self._buffer,
                max_header_bytes=self._max_header_bytes,
                max_payload_bytes=self._max_payload_bytes,
            ):
                self.frame_received.emit(header, payload)
        except FrameDecodeError as exc:
            _log.warning("IPC frame decode error: %s", exc)
            self.error.emit(str(exc))
            self.close()


class LocalIpcServer(QObject):
    client_connected = Signal(object)  # FramedLocalSocket
    error = Signal(str)

    def __init__(self, config: LocalSocketConfig, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._server = QLocalServer(self)

        QLocalServer.removeServer(self._config.server_name)
        if not self._server.listen(self._config.server_name):
            self.error.emit(f"Failed to listen on {self._config.server_name!r}")

        self._server.newConnection.connect(self._on_new_connection)

    @property
    def server_name(self) -> str:
        return self._config.server_name

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self._config.server_name)

    def _on_new_connection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return

        framed = FramedLocalSocket(socket, parent=self)
        token = self._config.token
        if token is None:
            self.client_connected.emit(framed)
            return

        handshaken = {"ok": False}

        def on_timeout() -> None:
            if not handshaken["ok"]:
                framed.close()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(on_timeout)
        timer.start(self._config.handshake_timeout_ms)

        def on_first_frame(header: dict[str, Any], payload: bytes) -> None:
            if header.get("kind") != "hello":
                framed.close()
                return
            if header.get("token") != token:
                framed.close()
                return

            handshaken["ok"] = True
            timer.stop()
            framed.frame_received.disconnect(on_first_frame)
            self.client_connected.emit(framed)

        framed.frame_received.connect(on_first_frame)


class LocalIpcClient(QObject):
    connected = Signal(object)  # FramedLocalSocket
    disconnected = Signal()
    error = Signal(str)

    def __init__(self, config: LocalSocketConfig, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._socket = QLocalSocket(self)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self.disconnected.emit)
        self._socket.errorOccurred.connect(lambda e: self.error.emit(str(e)))
        self._framed: FramedLocalSocket | None = None

    @property
    def framed(self) -> FramedLocalSocket | None:
        return self._framed

    def connect(self) -> None:
        self._socket.connectToServer(self._config.server_name)

    def close(self) -> None:
        self._socket.disconnectFromServer()

    def _on_connected(self) -> None:
        self._framed = FramedLocalSocket(self._socket, parent=self)
        if self._config.token is not None:
            self._framed.send({"kind": "hello", "token": self._config.token}, b"")
        self.connected.emit(self._framed)


@dataclass(frozen=True, slots=True)
class RpcResult:
    ok: bool
    result: Any = None
    error: str | None = None
    payload: bytes = b""


class RpcPeer(QObject):
    """
    Minimal RPC + event layer over `FramedLocalSocket`.

    - RPC requests/responses are correlated by `id`.
    - Handlers must be fast; schedule heavy work to background systems.
    """

    event_received = Signal(str, object, object)  # topic, data, payload
    rpc_completed = Signal(str, object)  # request_id, RpcResult

    def __init__(self, framed: FramedLocalSocket, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._framed = framed
        self._handlers: dict[str, Callable[[Any, bytes], Any]] = {}
        self._pending: dict[str, Callable[[RpcResult], None] | None] = {}
        self._timers: dict[str, QTimer] = {}

        self._framed.frame_received.connect(self._on_frame)
        self._framed.disconnected.connect(self._on_disconnected)

    def register(self, method: str, handler: Callable[[Any, bytes], Any]) -> None:
        self._handlers[method] = handler

    def send_event(self, topic: str, data: Any = None, payload: bytes = b"", *, meta: dict[str, Any] | None = None) -> None:
        self._framed.send(
            {
                "kind": "event",
                "topic": topic,
                "data": data,
                "meta": meta or {},
            },
            payload,
        )

    def call(
        self,
        request_id: str,
        method: str,
        params: Any = None,
        payload: bytes = b"",
        *,
        timeout_ms: int = 30_000,
        on_done: Callable[[RpcResult], None] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if request_id in self._pending:
            raise ValueError(f"Duplicate request_id: {request_id}")

        self._pending[request_id] = on_done

        timer = QTimer(self)
        timer.setSingleShot(True)

        def on_timeout() -> None:
            self._timers.pop(request_id, None)
            callback = self._pending.pop(request_id, None)
            result = RpcResult(ok=False, error=f"RPC timeout after {timeout_ms} ms")
            if callback is not None:
                callback(result)
            self.rpc_completed.emit(request_id, result)

        timer.timeout.connect(on_timeout)
        self._timers[request_id] = timer
        timer.start(timeout_ms)

        self._framed.send(
            {
                "kind": "rpc_request",
                "id": request_id,
                "method": method,
                "params": params,
                "meta": meta or {},
            },
            payload,
        )

    def _on_disconnected(self) -> None:
        pending = list(self._pending.items())
        self._pending.clear()
        for request_id, callback in pending:
            timer = self._timers.pop(request_id, None)
            if timer is not None:
                timer.stop()
            result = RpcResult(ok=False, error="IPC disconnected")
            if callback is not None:
                callback(result)
            self.rpc_completed.emit(request_id, result)

    def _on_frame(self, header: dict[str, Any], payload: bytes) -> None:
        kind = header.get("kind")
        if kind == "event":
            self.event_received.emit(str(header.get("topic", "")), header.get("data"), payload)
            return

        if kind == "rpc_response":
            request_id = str(header.get("id", ""))
            callback = self._pending.pop(request_id, None)
            timer = self._timers.pop(request_id, None)
            if timer is not None:
                timer.stop()
            result = RpcResult(
                ok=bool(header.get("ok")),
                result=header.get("result"),
                error=header.get("error"),
                payload=payload,
            )
            if callback is not None:
                callback(result)
            self.rpc_completed.emit(request_id, result)
            return

        if kind == "rpc_request":
            request_id = str(header.get("id", ""))
            method = str(header.get("method", ""))
            handler = self._handlers.get(method)
            if handler is None:
                self._framed.send(
                    {
                        "kind": "rpc_response",
                        "id": request_id,
                        "ok": False,
                        "error": f"Unknown method: {method}",
                    },
                    b"",
                )
                return

            try:
                result_value = handler(header.get("params"), payload)
                response_payload = b""
                if isinstance(result_value, tuple) and len(result_value) == 2:
                    result, response_payload = result_value
                else:
                    result = result_value
                self._framed.send(
                    {
                        "kind": "rpc_response",
                        "id": request_id,
                        "ok": True,
                        "result": result,
                        "error": None,
                    },
                    response_payload,
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._framed.send(
                    {
                        "kind": "rpc_response",
                        "id": request_id,
                        "ok": False,
                        "result": None,
                        "error": str(exc),
                    },
                    b"",
                )

