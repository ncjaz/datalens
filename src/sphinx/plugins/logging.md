# Logging (app + plugins)

DataLens V2 uses a single, central logging pipeline so app developers and plugin developers can diagnose issues quickly without blocking the UI.

## Key properties

- **Non-blocking**: log calls enqueue; file writes happen on a dedicated logging thread.
- **Bounded**: the log queue is size-limited; when full, new records are dropped rather than blocking the UI thread.
- **Attributed**: every record is enriched with fields like `layer`, `subsystem`, `execution`, and (when applicable) `plugin_id` and lifecycle `hook`.
- **Centralised**: there is one shared pipeline for the whole process (app + plugins).

## Where logs are written

Logs are written under the per-user DataLens data directory:

- Windows: `%LOCALAPPDATA%/datalens/logs/datalens.log`
- Linux: `$XDG_DATA_HOME/datalens/logs/datalens.log` (or `~/.local/share/datalens/logs/datalens.log`)

The file is rotated by size (see `datalens.core.logging.init_logging`).

You can disable file logging (stderr/console only) when launching the app:

`python -m datalens.app --no-log-file`

## Why the logging module lives in `datalens.core`

Logging is an infrastructure concern, but in V2 we treat `datalens.core` as the
home for **process-wide runtime primitives** that are safe to import from
anywhere (services, UI, infra helpers, plugin runtimes):

- No Qt dependency
- No DB or disk IO on import (initialisation is explicit via `init_logging()`)
- Used across layers (app, services, infra background workers, plugins)

This keeps the public import path stable for plugin authors:

```python
from datalens.core.logging import get_logger
```

If we later want stricter layering, we can move the implementation under
`datalens.infra` and keep `datalens.core.logging` as a thin facade/re-export.

## How to log (recommended)

Use the shared helper and a module-level logger:

```python
from datalens.core.logging import get_logger

log = get_logger(__name__)

def do_work() -> None:
    log.info("Hello from my plugin")
```

## When logs are saved (async pipeline)

Logging writes are asynchronous:

- your `log.info(...)` call is enqueued immediately (caller thread)
- a dedicated listener thread formats and writes to the log file
- logs are flushed/stopped at process exit via `atexit` (`shutdown_logging`)

If the log file cannot be opened, DataLens falls back to stderr-only logging and
emits a warning.

## Log levels

V2 uses standard Python levels:

- `DEBUG`: verbose diagnostics (internal state, timings, discovery details)
- `INFO`: normal lifecycle milestones (startup, plugin enable, project open/close)
- `WARNING`: recoverable problems and best-effort failures (e.g. derived metadata)
- `ERROR`: operation failures that may affect user work
- `CRITICAL`: unrecoverable failures (reserved for later)

The default configuration is set in `init_logging()`; it can be adjusted later
via settings/flags if needed.

### Operation-scoped logs (optional)

For multi-step flows, use `log_operation` to add a correlation id and consistent start/end/error messages:

```python
from datalens.core.logging import get_logger, log_operation

log = get_logger(__name__)

def migrate_something() -> None:
    with log_operation(subsystem="db", operation="migrate_plugin_tables", logger=log):
        ...
```

## Plugin lifecycle attribution (automatic)

When the plugin host calls plugin hooks (for example `on_load`, `on_project_opened`, `on_project_closing`), it binds context such as:

- `plugin_id`
- `hook`
- `plugin_phase`

This means logs emitted by plugin code during these hooks automatically carry the correct attribution.

## Background executor attribution (automatic)

Shared background executors capture and propagate the current logging context when work is submitted:

- `ProjectDb.execute_read/execute_write` (DB thread)
- `IoWriter.submit` and helpers (IO thread)
- loader tasks run via `run_with_loader` (loader worker thread)

If a plugin schedules DB/IO work during a hook, the scheduled work inherits the same `plugin_id`/`hook` context.

## Advanced: binding extra fields

If you need to attach additional fields to a block of logs:

```python
from datalens.core.logging import bind_log_context, get_logger

log = get_logger(__name__)

with bind_log_context(subsystem="streaming", stream_key="capture.rgb"):
    log.info("Publishing frame")
```

## Don't log high-rate data

Avoid logging per-frame/per-sample information in tight loops (video, streaming, model inference).
Prefer periodic summaries and counters.
