from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QTimer

from datalens.infra.ipc.process_runner import LocalWorkerProcess, WorkerProcessSpec
from datalens.infra.ipc.protocol import new_request_id


def main() -> int:
    app = QCoreApplication(sys.argv)

    worker = LocalWorkerProcess(WorkerProcessSpec(module="datalens.infra.ipc.examples.echo_worker"))
    worker.stdout_text.connect(lambda s: print(f"[worker stdout] {s}", end=""))
    worker.stderr_text.connect(lambda s: print(f"[worker stderr] {s}", end="", file=sys.stderr))
    worker.error.connect(lambda s: print(f"[host] worker error: {s}", file=sys.stderr))

    def on_connected(rpc) -> None:
        print("[host] worker connected")

        rpc.event_received.connect(lambda topic, data, payload: print(f"[host] event {topic}: {data}"))

        def on_pong(result) -> None:
            print(f"[host] rpc result: ok={result.ok} result={result.result} error={result.error}")

        rpc.call(new_request_id(), "ping", {"hello": "world"}, on_done=on_pong)

    worker.connected.connect(on_connected)
    worker.exited.connect(lambda code, status: print(f"[host] worker exited code={code} status={status}"))

    worker.start()

    QTimer.singleShot(4_000, lambda: worker.stop())
    QTimer.singleShot(6_000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

