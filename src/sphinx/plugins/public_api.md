# Plugin public API (stable imports)

When writing plugins, prefer importing from `datalens.api` instead of reaching
into internal modules under `datalens.services.*` / `datalens.ui.*`.

Why:

- V2 is still evolving: internal module layout will move as we split files and
  harden boundaries.
- A stable import surface keeps plugins from churning as the app grows.

## Recommended imports

Use:

```python
from datalens.api.plugins import (
    PluginId,
    ProjectAwarePlugin,
    PluginAppContext,
    PluginProjectContext,
    PluginMigration,
    run_plugin_migrations,
)
```

For UI bindings that pair a shortcut command with a button/menu/checkbox/toggle, use:

```python
from datalens.api.ui_commands import ShortcutButtonBinding, ShortcutButtonCommand
```

Avoid:

```python
from datalens.services.plugins.runtime.contracts import ProjectAwarePlugin  # unstable path
```

## Threading rule (non-negotiable)

**Never touch Qt widgets from non-UI threads.**

- Plugin hooks are often called from background loader stages.
- If you need to update UI, marshal back to the Qt thread (signals, or
  `QTimer.singleShot(0, ...)`).

## Non-blocking rule (non-negotiable)

Do not block the UI thread waiting on:

- DB futures (`Future.result(...)`)
- command futures
- network calls
- file I/O

If you have a `Future`, attach a callback or use a loader stage to run the
work off-thread.

## Plugin preferences

Plugins can store persisted, user-editable preferences under `settings.json` and
expose them in the Preferences UI via the plugin manifest (no runtime import).

- Runtime access: `ctx.app.preferences`
- Docs: `plugins/preferences.md`
