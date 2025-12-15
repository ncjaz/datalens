from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from datalens.infra.ipc.local_socket import LocalIpcClient, LocalSocketConfig, RpcPeer


@dataclass(frozen=True, slots=True)
class WorkerIpcEnv:
    server_name: str
    token: str

    @staticmethod
    def from_env() -> "WorkerIpcEnv":
        server_name = os.environ.get("DATALENS_IPC_SERVER_NAME")
        token = os.environ.get("DATALENS_IPC_TOKEN")
        if not server_name or not token:
            raise RuntimeError(
                "Missing IPC env vars; expected DATALENS_IPC_SERVER_NAME and DATALENS_IPC_TOKEN"
            )
        return WorkerIpcEnv(server_name=server_name, token=token)


class WorkerIpcClient(QObject):
    """
    Convenience wrapper for worker processes to connect back to the host.

    Usage:

    - construct after creating a `QCoreApplication`
    - connect to `ready` to register RPC handlers / start timers
    - call `connect()` to initiate the socket connection
    """

    ready = Signal(object)  # RpcPeer
    error = Signal(str)

    def __init__(self, env: WorkerIpcEnv | None = None, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._env = env or WorkerIpcEnv.from_env()
        self._client = LocalIpcClient(
            LocalSocketConfig(server_name=self._env.server_name, token=self._env.token),
            parent=self,
        )
        self._client.error.connect(self.error.emit)
        self._client.connected.connect(self._on_connected)
        self._rpc: RpcPeer | None = None

    @property
    def rpc(self) -> RpcPeer | None:
        return self._rpc

    def connect(self) -> None:
        self._client.connect()

    def _on_connected(self, framed_socket) -> None:
        self._rpc = RpcPeer(framed_socket, parent=self)
        self.ready.emit(self._rpc)

