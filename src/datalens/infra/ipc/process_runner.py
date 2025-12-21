from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from datalens.infra.ipc.local_socket import LocalIpcServer, LocalSocketConfig, RpcPeer
from datalens.infra.ipc.protocol import new_endpoint_name

_log = logging.getLogger(__name__)

def _find_repo_root(start: Path) -> Path:
    """
    Best-effort repo root discovery for worker processes.

    Prefer passing `WorkerProcessSpec.working_dir`. This fallback exists to make
    local development resilient if files move within the package tree.
    """
    markers = ("pyproject.toml", "requirements.txt", ".git")
    current = start.resolve()
    for candidate in (current, *current.parents):
        for marker in markers:
            if (candidate / marker).exists():
                return candidate
    return current


@dataclass(frozen=True, slots=True)
class WorkerProcessSpec:
    """
    Specification for a Python worker started via `QProcess`.

    The worker is started with environment variables that describe how to connect
    back to the host IPC server (local socket name + token).
    """

    module: str
    args: list[str] = field(default_factory=list)
    working_dir: Path | None = None
    env: dict[str, str] = field(default_factory=dict)


class LocalWorkerProcess(QObject):
    """
    Spawn a Python worker process and accept its IPC connection (local socket).

    This is the recommended building block for “service plugins” that want to
    offload heavy work (watchers, capture, indexing, training) into a separate
    process while keeping the UI responsive.
    """

    connected = Signal(object)  # RpcPeer
    stdout_text = Signal(str)
    stderr_text = Signal(str)
    exited = Signal(int, int)  # exit_code, exit_status
    error = Signal(str)

    def __init__(
        self,
        spec: WorkerProcessSpec,
        *,
        server_name: str | None = None,
        token: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._spec = spec
        self._server_name = server_name or new_endpoint_name("datalens-ipc")
        self._token = token or new_endpoint_name("token")

        self._server = LocalIpcServer(LocalSocketConfig(self._server_name, token=self._token), parent=self)
        self._server.error.connect(self.error.emit)
        self._server.client_connected.connect(self._on_client_connected)

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(lambda e: self.error.emit(str(e)))

        self._rpc: RpcPeer | None = None
        self._kill_timer: QTimer | None = None

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def token(self) -> str:
        return self._token

    @property
    def rpc(self) -> RpcPeer | None:
        return self._rpc

    def start(self) -> None:
        if self._process.state() != QProcess.NotRunning:
            raise RuntimeError("Worker process already running")

        working_dir = self._spec.working_dir
        if working_dir is None:
            working_dir = _find_repo_root(Path.cwd())
        self._process.setWorkingDirectory(str(working_dir))

        env = QProcessEnvironment.systemEnvironment()
        env.insert("DATALENS_IPC_SERVER_NAME", self._server_name)
        env.insert("DATALENS_IPC_TOKEN", self._token)
        for key, value in self._spec.env.items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)

        self._process.setProgram(sys.executable)
        self._process.setArguments(["-m", self._spec.module, *self._spec.args])

        _log.info("Starting worker process: %s", self._spec.module)
        self._process.start()

    def stop(self, *, terminate_timeout_ms: int = 2_000) -> None:
        if self._process.state() == QProcess.NotRunning:
            self._cleanup()
            return

        self._process.terminate()

        timer = QTimer(self)
        timer.setSingleShot(True)

        def on_kill() -> None:
            if self._process.state() != QProcess.NotRunning:
                self._process.kill()

        timer.timeout.connect(on_kill)
        timer.start(terminate_timeout_ms)
        self._kill_timer = timer

    def _cleanup(self) -> None:
        self._rpc = None
        self._server.close()

    def _on_client_connected(self, framed_socket) -> None:
        self._rpc = RpcPeer(framed_socket, parent=self)
        self.connected.emit(self._rpc)

    def _on_stdout(self) -> None:
        data = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        if data:
            self.stdout_text.emit(data)

    def _on_stderr(self) -> None:
        data = bytes(self._process.readAllStandardError()).decode(errors="replace")
        if data:
            self.stderr_text.emit(data)

    def _on_finished(self, exit_code: int, exit_status) -> None:  # pragma: no cover - Qt enum typing varies
        if self._kill_timer is not None:
            self._kill_timer.stop()
            self._kill_timer = None
        self._cleanup()
        self.exited.emit(int(exit_code), int(exit_status))
