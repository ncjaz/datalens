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

## Toast Notifications

Show lightweight, non-blocking notifications to provide user feedback:

```python
from datalens.services.notifications.toast_service import (
    show_success,
    show_warning,
    show_error,
    show_info,
)

# Success notification (5s duration, green checkmark icon)
show_success("Export Complete", "File saved to Desktop/export.csv")

# Warning notification (7s duration, yellow warning icon)
show_warning("Memory Low", "Consider closing unused projects")

# Error notification (10s duration, red X icon)
show_error("Export Failed", "Disk full or permission denied")

# Info notification (5s duration, blue info icon)
show_info("Processing Started", "This may take a few minutes")
```

**Key features:**
- **Non-blocking**: Returns immediately, toast created asynchronously
- **Thread-safe**: Safe to call from any thread
- **Auto-positioning**: Automatic stacking at 9 screen positions
- **Queue management**: Up to 3 visible, 10 queued toasts
- **Size constraints**: 300-400px width, 80-150px height
- **Animations**: Smooth slide + fade in/out

**Advanced usage:**

```python
from datalens.ui.widgets.notifications.toast_manager import ToastManager
from datalens.ui.widgets.notifications.toast_types import ToastIconType, ToastPosition

manager = ToastManager.get_instance()

manager.show_toast(
    title="Custom Toast",
    message="Custom settings",
    icon_type=ToastIconType.SUCCESS,
    duration=8000,  # 8 seconds (0 = manual close only)
    position=ToastPosition.TOP_RIGHT,
)
```

**Best practices:**
- Keep titles to 1-5 words, messages to 1-2 sentences
- Use for completion feedback, non-critical warnings, background notifications
- Don't use for critical errors requiring user action (use dialogs instead)
- Default position is `BOTTOM_RIGHT` - only override for specific use cases

**Full documentation:**
- Detailed guide: `plugins/toast_notifications.md`
- How it works: Singleton manager, queue management, window following, animations

## Plugin preferences

Plugins can store persisted, user-editable preferences under `settings.json` and
expose them in the Preferences UI via the plugin manifest (no runtime import).

- Runtime access: `ctx.app.preferences`
- Docs: `plugins/preferences.md`
