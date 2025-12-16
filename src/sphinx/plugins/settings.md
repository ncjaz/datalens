# Plugin settings (settings.json)

DataLens persists lightweight app + plugin settings in a per-user JSON file:

- Location is `datalens.infra.paths.settings_json_path()`
- Schema is `datalens.domain.settings.AppSettings`
- Per-plugin settings live under `AppSettings.plugin_settings` keyed by plugin ID

## Updating settings safely

Use the settings helpers so updates are atomic (load → replace → save) and safe
to call from background threads:

```python
from dataclasses import replace

from datalens.services.config_service import update_settings

def enable_my_feature(settings):
    plugin_id = "my_plugin"
    plugin_settings = dict(settings.plugin_settings)
    plugin_settings[plugin_id] = {**plugin_settings.get(plugin_id, {}), "enabled": True}
    return replace(settings, plugin_settings=plugin_settings)

update_settings(enable_my_feature)
```

If you need higher-level helpers, prefer building them on top of
`datalens.services.settings_store.SettingsStore` (or `DebouncedSettingsWriter`
for coalesced background writes).
