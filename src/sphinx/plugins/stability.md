---
orphan: true
---

# Plugin API stability (what you can rely on)

This page defines the **plugin-facing API surface that DataLens V2 intends to keep stable** as plugins are developed.
If something is not listed here, treat it as **internal** and subject to change.

## Stable import surface

Plugins should prefer importing from:

- `datalens.api.plugins`

This module exists specifically to avoid plugin code needing to chase internal refactors.

### What is stable today

From `datalens.api.plugins`:

- **Lifecycle base classes & hooks**
  - `BasePlugin`
  - `ProjectAwarePlugin`
  - `SupportsShortcuts`
- **Runtime contexts**
  - `PluginAppContext`
  - `PluginProjectContext`
- **Identifiers/metadata**
  - `PluginId`, `PluginDefinition`, `PluginKind`, `PluginStage`
- **Persistence**
  - `PluginDb`
  - plugin migrations: `PluginMigration`, `run_plugin_migrations`, `PluginMigrationError`
- **Non-blocking file I/O**
  - `IoWriter`
- **Shortcuts contracts (declarations)**
  - `ShortcutPageSpec`, `ShortcutSectionSpec`, `ShortcutCommandSpec`, `GestureBindingSpec`
  - `ShortcutChord`, `ShortcutCommandId`, `GestureId`, `GesturePhase`, `ShortcutScope`

### What is explicitly *not* stable

- Anything under `datalens.services.*` unless it’s re-exported through `datalens.api.plugins`.
- Any UI modules (`datalens.ui.*`) except where explicitly documented as a plugin integration surface.
- Any `datalens.infra.*` helpers (these are implementation details).

## Threading rule (must follow)

**Never touch Qt widgets (or any Qt GUI object) from a background thread.**

If your plugin needs long-running work:

1. Run work in a loader/background task.
2. Marshal results back to the UI thread before updating widgets.

Canonical pattern:

```python
from PySide6.QtCore import QTimer

def do_heavy_work_in_background() -> dict:
    ...

def on_result_ready(widget, result: dict) -> None:
    # UI thread only
    widget.setText(str(result))

result = do_heavy_work_in_background()
QTimer.singleShot(0, lambda: on_result_ready(my_widget, result))
```

If you violate this rule, you may see:

- hard crashes (process exits / access violations)
- silent UI corruption
- random freezes

## Loader UX vs logging

Loader tasks can emit user-facing progress via:

- `LoaderContext.log(...)` when you are writing top-level orchestration code **that knows** it is running under a loader.
- `log.progress(...)` from deeper utility code (optional UX signal) when you **don’t** want to thread a `LoaderContext` through your call stack.

The loader can be configured to display some log levels and/or `ctx.log` messages.

See {doc}`../ui/loader` for details.
