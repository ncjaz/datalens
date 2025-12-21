# Plugin preferences (manifest-driven)

DataLens V2 supports **plugin-defined, persisted preferences** that:

- are declared in the plugin `manifest.json` (`preferences` block)
- render automatically under **Preferences → Plugins**
- persist under `settings.json` (`AppSettings.plugin_settings`)
- are visible in **Help → States** (preferences snapshot)

This system is designed to be **safe with disabled plugins**: the schema is read
at discovery time from the manifest, so DataLens can display preferences without
importing the plugin runtime code.

## Why manifest-driven?

The core constraint is: **plugins must not import each other**, and disabled
plugins must not be imported at all.

If schemas lived in Python modules, the app would have to import plugin code
just to build Preferences UI, which breaks those constraints.

## Manifest schema (v0)

The schema is JSON-only and intentionally small (it can expand later).

Example:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "preferences": {
    "schema_version": 1,
    "title": "My Plugin",
    "sections": [
      {
        "id": "general",
        "title": "General",
        "fields": [
          {
            "key": "enabled",
            "title": "Enabled",
            "kind": "bool",
            "default": true
          },
          {
            "key": "mode",
            "title": "Mode",
            "kind": "enum",
            "default": "fast",
            "options": [
              { "id": "fast", "label": "Fast" },
              { "id": "accurate", "label": "Accurate" }
            ]
          }
        ]
      }
    ]
  }
}
```

Supported kinds:

- `bool`
- `enum`
- `toggle` (2-option enum rendered as a toggle)
- `int`, `float`
- `string`
- `path`

## Reading and reacting in plugin code

Plugins access preferences through `PluginAppContext.app`:

```python
from datalens.domain.plugin import PluginId

MY_PLUGIN_ID = PluginId("my_plugin")

def on_load(self, ctx):
    enabled = ctx.app.preferences.get(MY_PLUGIN_ID, "enabled", default=True)
```

To react to user edits without polling:

```python
def on_load(self, ctx):
    def on_changed(_pid, keys):
        if "enabled" in keys:
            ...

    self._unsub = ctx.app.preferences.subscribe(MY_PLUGIN_ID, on_changed)
```

Notes:

- `subscribe(...)` callbacks are delivered via the **EventHub** and run on the UI
  thread (queued delivery), so callbacks must be quick.
- Writes are **debounced** and run off the UI thread.

## State and diagnostics

The States inspector includes a `preferences` subtree (snapshot from
`PluginPreferencesService.snapshot()`), which is the single source of truth for
debugging what the app believes is effective.

