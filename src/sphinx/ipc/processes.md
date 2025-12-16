# Worker processes with `QProcess`

For out-of-process work, V2 uses Qt’s `QProcess` so it behaves consistently on
Windows/macOS/Linux.

The core wrapper is:

- `datalens.infra.ipc.process_runner.LocalWorkerProcess`

It combines:

- process start/stop (`QProcess`)
- an IPC server (`QLocalServer`)
- a connected RPC peer (`RpcPeer`) once the worker connects

## Minimal example: start a worker and receive events

Host process (UI-side):

```python
from PySide6.QtCore import QCoreApplication
from datalens.infra.ipc.process_runner import LocalWorkerProcess, WorkerProcessSpec

app = QCoreApplication([])

worker = LocalWorkerProcess(
    WorkerProcessSpec(module="datalens.infra.ipc.examples.echo_worker")
)
worker.connected.connect(lambda rpc: print("connected"))
worker.start()

app.exec()
```

Worker process (service-side) reads its IPC connection info from environment:

- `DATALENS_IPC_SERVER_NAME`
- `DATALENS_IPC_TOKEN`

Use:

- `datalens.infra.ipc.worker_bootstrap.WorkerIpcClient`

## Output example

Running the demo host:

```bash
python -m datalens.infra.ipc.examples.echo_host
```

Expected output (example):

```text
[host] worker connected
[host] rpc result: ok=True result={'pong': True, 'params': {'hello': 'world'}} error=None
[host] event worker.ready: {'pid': 12345}
[host] event tick: {'ts': '2025-12-15T12:00:00'}
```

## Shutdown rules

- Never block the UI thread waiting for the worker.
- Use `LocalWorkerProcess.stop()` (terminate + kill after timeout).
- Workers should flush/close resources before exit (DB/IO, shared memory, etc.).

## Plugin usage pattern (recommended)

In a UI plugin, UI callbacks should only *schedule* work:

```python
from datalens.infra.ipc.protocol import new_request_id

def on_button_clicked() -> None:
    if worker.rpc is None:
        return
    worker.rpc.call(new_request_id(), "index.scan", {"root": str(project_root)})
```

Keep UI state updates on the UI thread; keep I/O and heavy CPU in the worker process.
