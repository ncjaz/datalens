# Plugin UI presentation (welcome screen)

The plugin runtime exposes `PluginDefinition` metadata which the welcome screen
uses to render plugin cards and feature toggles.

## Metadata sources

- `PluginDefinition.name`, `description`, `version`, `author`, `homepage`
- `PluginDefinition.features` (tabs/services/datasources/models)
- `PluginDefinition.group` (optional)
- `PluginDefinition.manual_pip_requirements` (optional)

## Grouped plugins

If `group` is set, the welcome UI can render plugins in a grouped layout:

- Sort by `group` then plugin name.
- Render group header once.
- Render a shared outline around the contiguous cards.

If `group` is missing, the plugin is rendered as a standalone card.

## UI state persistence (QSettings)

Persist plugin *UI layout/geometry state* using Qt `QSettings` (not `settings.json`).

Rules:

- Namespace keys by plugin id so plugins can be enabled/disabled without collisions:
  `plugins/<plugin_id>/ui/...`
- Use `saveGeometry()` / `restoreGeometry()` for windows/dialogs and `saveState()` / `restoreState()` for splitters/docks.

Example (dialog geometry):

```python
from datalens.ui.qt_settings import plugin_ui_scope

plugin_id = "capture"  # or `str(ctx.plugin.id)`
scope = plugin_ui_scope(plugin_id, "my_dialog")

# On open/show:
scope.restore_geometry("geometry", dialog)

# On close:
scope.save_geometry("geometry", dialog)
```

## Dependencies

For plugins with a `requirements.txt` and/or `manual_pip_requirements`, show:

- availability status (installed / missing / incompatible)
- install button (runs the shared installer workflow)
- a short explanation of what will be installed

If `manual_pip_requirements` is non-empty, also show:

- a “manual install required” section with a link/instructions (e.g. PyTorch
  selector), since the correct wheel may be OS/CUDA-specific.
