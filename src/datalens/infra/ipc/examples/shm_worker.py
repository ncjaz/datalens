from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QTimer

from datalens.infra.ipc.shared_memory import SharedMemoryLatestBuffer
from datalens.infra.ipc.worker_bootstrap import WorkerIpcClient


def main() -> int:
    app = QCoreApplication(sys.argv)

    client = WorkerIpcClient()
    shm = SharedMemoryLatestBuffer.create(slot_count=8, slot_bytes=1024)

    counter = {"n": 0}

    def on_ready(rpc) -> None:
        rpc.send_event("worker.ready", {"pid": app.applicationPid(), "shm": shm.name})

        def publish() -> None:
            counter["n"] += 1
            payload = f"blob #{counter['n']}".encode("utf-8")
            ptr = shm.publish(payload)
            rpc.send_event("blob", {"ptr": ptr.to_dict()})

        timer = QTimer(client)
        timer.setInterval(250)
        timer.timeout.connect(publish)
        timer.start()

    client.ready.connect(on_ready)
    client.error.connect(lambda msg: print(f"[worker] ipc error: {msg}", file=sys.stderr))
    client.connect()

    exit_code = app.exec()
    shm.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

