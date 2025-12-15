from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QTimer

from datalens.infra.ipc.process_runner import LocalWorkerProcess, WorkerProcessSpec
from datalens.infra.ipc.shared_memory import SharedMemoryLatestBuffer, SharedMemoryPointer


def main() -> int:
    app = QCoreApplication(sys.argv)

    worker = LocalWorkerProcess(WorkerProcessSpec(module="datalens.infra.ipc.examples.shm_worker"))
    shm: SharedMemoryLatestBuffer | None = None

    def on_connected(rpc) -> None:
        nonlocal shm
        print("[host] worker connected")

        def on_event(topic: str, data: object, payload: object) -> None:
            nonlocal shm
            if topic != "blob":
                return
            if not isinstance(data, dict):
                return
            ptr_raw = data.get("ptr")
            if not isinstance(ptr_raw, dict):
                return
            ptr = SharedMemoryPointer.from_dict(ptr_raw)
            if shm is None:
                shm = SharedMemoryLatestBuffer.attach(ptr.name)
            blob = shm.read(ptr).decode("utf-8", errors="replace")
            print(f"[host] {blob}")

        rpc.event_received.connect(on_event)

    worker.connected.connect(on_connected)
    worker.start()

    QTimer.singleShot(2_000, worker.stop)
    QTimer.singleShot(3_000, app.quit)
    exit_code = app.exec()
    if shm is not None:
        shm.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

