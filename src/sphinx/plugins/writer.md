# Persistence: ProjectDb + IoWriter (non-blocking)

This page describes the V2 persistence pattern for non-blocking project writes:

- SQLite via `ProjectDb` (authoritative project state)
- file IO via `IoWriter` (small/medium derived artifacts, exports, caches)

## Goals

- Plugins can persist project state without freezing the UI.
- Plugins do not import each other (writes are namespaced by plugin id).
- SQLite access is thread-safe and predictable.
- The API supports an upgrade path (single-thread DB now -> read pooling later) without forcing plugin refactors.

## Runtime access (plugin-facing)

Project persistence is gated on whether a project is open.

Today, the concrete runtime types are:

- `datalens.core.context.AppContext`
- `datalens.core.context.ProjectContext`
- `datalens.services.db.project_db.ProjectDb`

When a project is open:

- `ctx.require_project().project_db` provides the per-project DB interface.

Example (KV store):

```python
from datalens.domain.plugin import PluginId

def save_something(ctx) -> None:
    project = ctx.require_project()  # raises if no project is open
    db = project.project_db
    db.kv_set(PluginId("my_plugin"), "example_key", {"enabled": True})
```

Important UI rule:

- `ProjectDb` methods return `concurrent.futures.Future`.
- Do not call `future.result()` on the UI thread.

If you need to update UI when a Future completes, attach a callback and hop back to the UI thread.
One minimal pattern (Qt):

```python
from PySide6.QtCore import QTimer

def on_future_done(fut, *, on_ui_thread):
    def run():
        try:
            value = fut.result()
        except Exception as exc:
            on_ui_thread(error=exc)
        else:
            on_ui_thread(value=value)
    QTimer.singleShot(0, run)
```

## Implementation overview (layers)

### 1) DB gateway (low-level)

`datalens.services.db.gateway` is a thin wrapper around `sqlite3.Connection`:

- opens the connection
- applies pragmas (WAL, foreign_keys, busy_timeout)
- provides small helpers: `execute`, `query_one`, `query_all`, `transaction`

### 2) Core schema + migrations (core-owned tables only)

`datalens.services.db.migrations_runner` owns core schema creation/migrations.

Core-owned tables (reserved):

- `app_meta`
- `plugin_kv`

The core app must never migrate or modify plugin-owned tables.

### 3) Project DB executor (`ProjectDb`)

`datalens.services.db.project_db` provides the non-blocking execution model for SQLite:

- a single background thread
- one SQLite connection used by that thread
- queued `execute_write(fn(conn))` calls
- queued `execute_read(fn(conn))` calls (initially on the same thread for simplicity)

Later, `execute_read(...)` can be upgraded to use separate read connections behind the same API.

`SqliteProjectDb` initializes asynchronously and exposes `ready()` (a Future). The project open flow should wait
for readiness in a background stage (loader), not on the UI thread.

### 4) Async file IO (`IoWriter`)

For non-blocking file writes (small JSON/manifests), V2 uses:

- `datalens.services.background_io.writer.IoWriter`

It provides atomic helpers:

- `write_json_atomic(path, payload)`
- `write_text_atomic(path, text)`
- `write_bytes_atomic(path, data)`

## Plugin-facing API (preferred)

Plugins should primarily use prebuilt helpers rather than writing raw SQL:

- plugin KV store (key-value)
  - `(plugin_id, key) -> value_json`
  - use for small per-plugin project state
- repositories for structured plugin tables
  - annotation tables, capture sessions, etc.

## Raw SQL escape hatch

For advanced use cases, plugins may execute SQL directly through the project DB service:

- `execute_read(fn(conn))`
- `execute_write(fn(conn))`

The important constraint is that the plugin still uses the injected project DB service, so the UI stays responsive
and SQLite thread-safety is maintained.

## Namespacing and plugin-owned tables

Every plugin has a stable `plugin_id` (defined by the plugin base/manifest).

The host uses this to:

- namespace KV keys
- preserve data even if a plugin is disabled/offline

Recommended table naming for plugin-owned tables:

- prefix table names with the plugin id (or a standard scheme we adopt), to avoid collisions

## Project close (plugin flush)

If your plugin starts its own background workers (capture pipelines, exporters,
model runtimes), it should expose a flush/stop operation and register a
project-close hook so the host can flush before closing the DB:

- `AppContext.register_project_flush_hook(hook)`

Future: plugin version tracking

- V2 plans to add a core-owned `plugin_meta` table where plugins can record their own `plugin_version` and `schema_version` (plugins own their row; core owns only the table).
