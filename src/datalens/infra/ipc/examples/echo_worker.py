from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QCoreApplication, QTimer

from datalens.infra.ipc.worker_bootstrap import WorkerIpcClient


def main() -> int:
    app = QCoreApplication(sys.argv)

    client = WorkerIpcClient()

    def on_ready(rpc) -> None:
        rpc.register("ping", lambda params, payload: {"pong": True, "params": params})

        timer = QTimer(client)
        timer.setInterval(1_000)
        timer.timeout.connect(
            lambda: rpc.send_event(
                "tick",
                {"ts": datetime.now().isoformat(timespec="seconds")},
            )
        )
        timer.start()

        rpc.send_event("worker.ready", {"pid": app.applicationPid()})

    client.ready.connect(on_ready)
    client.error.connect(lambda msg: print(f"[worker] ipc error: {msg}", file=sys.stderr))
    client.connect()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

