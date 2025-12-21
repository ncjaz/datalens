# Logging system (V2 plan)

This document defines the V2 plan for a **centralised, plugin-aware logging system** with a focus on:

- performance (no UI freezes; bounded backpressure)
- correctness (no silent failure; predictable formatting)
- ergonomics (minimal boilerplate for app + plugin developers)

## Objective

Establish a single logging pipeline that:

1. is **non-blocking** for the Qt UI thread and other critical threads
2. writes logs to a **rotating file** under the user data dir
3. provides strong **attribution** (app vs plugin, subsystem, background vs UI)
4. lets plugins (and shared systems like DB/IO) participate without imports between plugins

## Robustness contract (non-negotiables)

### 1) Never block the UI thread on logging I/O

- Log calls must be O(1) and enqueue-only on the caller thread.
- File writes happen on a dedicated logging thread.
- If the log queue is full, drop low-priority logs rather than blocking UI.

### 2) Attribution must be visible at first glance

Every log record should include (explicitly or inferred):

- `layer`: `app|ui|service|infra|plugin|domain`
- `subsystem`: `plugins|project|db|io|settings|background|streaming|commands|events|models|...`
- `component`: module/class/owner name
- `execution`: `ui|background|db|io`
- `plugin_id`: `-` for core logs; plugin ID string for plugin logs

Optional fields are attached when relevant (e.g. plugin hook invocations, migrations, streaming):

- `hook`: `on_load|on_project_opened|on_project_closing|...`
- `plugin_phase`: `enable|project_open|project_close|flush|...`
- `op_id`: correlation id across a multi-stage operation
- subsystem-specific fields like `db_path`, `table`, `path`, `event_name`, `stream_key`

### 3) Shared background systems must preserve attribution

When the app/plugin schedules work onto shared background executors, the logging context must
propagate to that thread:

- `ProjectDb.execute_*` work on the DB thread carries the caller context.
- `IoWriter.submit` work on the IO thread carries the caller context.
- Loader worker tasks (`LoaderWorker`) carry the caller context.

## Design

### Asynchronous pipeline

Use Python's built-in logging stack:

```
Logger -> QueueHandler (non-blocking) -> QueueListener thread -> RotatingFileHandler (+ optional StreamHandler)
```

The queue is bounded; a custom handler drops records on overflow (with a minimal stderr notice).

### Context propagation

Use `contextvars` to hold current context (plugin id, op id, hook info, etc.).
Shared executors capture `contextvars.copy_context()` at submission time and run the task under that context.

### Inference rules (reduce boilerplate)

Default `layer`/`subsystem`/`component` can be inferred from the logger name (`__name__`) using a
prefix mapping (e.g. `datalens.services.db.* -> subsystem=db`).

`execution` is inferred from the current thread:

- main thread -> `ui`
- DB thread name prefix -> `db`
- IO thread name -> `io`
- otherwise -> `background`

## Public API (stable)

Core module: `datalens/core/logging.py`

- `init_logging(...) -> LoggingSystem`
- `get_logger(name=__name__, **bind) -> LoggerAdapter`
- `bind_log_context(**fields)` context manager (contextvars)
- `log_operation(subsystem, operation, **fields)` context manager (adds op_id + start/end/error logs)
- `shutdown_logging()` to flush/stop the listener thread

## Implementation tasks + status

### 1) Core logging module (`datalens/core/logging.py`)

Responsibilities:

- configure async queue-based logging + rotation
- install record enrichment (layer/subsystem/component/execution defaults)
- expose `get_logger` + context binding helpers

Status: implemented.

### 2) Propagate context in shared executors

- `services/db/project_db.py`: store `copy_context()` per task and run under it
- `services/background_io/writer.py`: store `copy_context()` per task and run under it
- `infra/background/loader_worker.py`: capture context at `start()` and run task under it

Status: implemented.

### 3) Wire into app + plugin lifecycle

- `datalens/app.py`: call `init_logging()` early (before Qt import is fine)
- replace `print(..., file=sys.stderr)` with structured logging
- `services/plugins/host.py`: wrap hook invocations in `bind_log_context(plugin_id=..., hook=..., plugin_phase=...)`

Status: implemented.

### 4) Documentation (Sphinx)

- Add a short page explaining how to log (app + plugin dev) and what fields mean.
- Document the non-blocking + queue drop policy.

Status: implemented.

## Correctness criteria (must be true)

- Logging never blocks the UI thread (no direct disk I/O in UI thread).
- Logs appear in the rotating file under the user data dir (when writable).
- Plugin logs are attributed with `plugin_id` (during hooks and scheduled work).
- DB/IO executor logs preserve the caller context (plugin id + hook/op metadata).
- If logging file output cannot be initialised, the app still runs and logs to stderr.

## Failure modes

- Log directory not writable: fall back to stderr-only logging and emit one warning.
- Log queue full: drop new records and emit an occasional stderr warning (no recursion into logging).
- Misbehaving plugin spams logs: bounded queue prevents unbounded memory growth.

## Validation steps

- `python -m compileall -q datalens/src/datalens`
- smoke import: `python -c "from datalens.core.logging import init_logging; init_logging();"`
- run `python -m datalens.app` and confirm `.../datalens/logs/datalens.log` is created and receives entries
