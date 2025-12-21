# Loader dialog (run_with_loader)

DataLens V2 uses a small, frameless loader dialog for long-running tasks that must not block the Qt UI thread.

This system is used for:

- startup stages (settings, plugin enable, project open)
- project open/switch/close flows
- any plugin work that needs user feedback (file discovery, migrations, etc.)

## Core API

- Runner: `datalens.infra.background.loader_runner.run_with_loader`
- Task context: `datalens.infra.background.loader_context.LoaderContext`
- UI: `datalens.ui.widgets.dialogs.loader_dialog.LoaderDialog`

The task always runs on a background `QThread`. The dialog updates happen on the UI thread via Qt signals.

## Two message channels

### 1) Task messages (`ctx.log(...)`)

Inside a loader task:

```python
def task(ctx: LoaderContext) -> object:
    ctx.log("Opening project…")
    ...
```

This is an explicit status channel. It is always safe and does not require a logger.

### 2) Progress logs (`log.progress(...)`)

Any code running under a loader (including deep utility functions that don't accept `ctx`) can emit a user-facing
status line by logging with a progress flag:

```python
log.progress("Indexing images…")
```

This log line is written to the normal log output *and* mirrored into the active loader dialog (best-effort).

If `plugin_id` is available in logging context, the dialog shows:

- `<plugin_id>: Indexing images…`

Otherwise, the logger name is used as a best-effort prefix.

#### Optional: progress bar updates

`log.progress(...)` also supports an optional progress value:

```python
log.progress("Indexing images…", value=0.4)  # 0..1
```

Use this sparingly. Prefer a single orchestrator to drive overall progress to avoid competing writers.

## Cancellation

Cancellation is cooperative:

- the UI can request cancel (Cancel button)
- the task must periodically check `ctx.is_cancel_requested()` / `ctx.raise_if_cancelled()`

Only enable cancel when the task is actually cancellable:

```python
run_with_loader(
    parent=self,
    title="Discovering files…",
    task=discover_task,
    dialog_options={"cancelable": True},
)
```

## Preferences (User Interface → Loader)

Preferences control what is mirrored into the loader dialog:

- `ctx.log(...)` messages
- `log.progress(...)` messages
- optionally: INFO/WARNING/ERROR/CRITICAL logs (defaults off to avoid spam)

These toggles affect only the loader dialog. They do not change what gets written to the log file.

