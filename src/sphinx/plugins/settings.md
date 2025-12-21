# Plugin settings (settings.json)

DataLens persists lightweight app + plugin settings in a per-user JSON file:

- Location is `datalens.infra.paths.settings_json_path()`
- Schema is `datalens.domain.system.settings.AppSettings`
- Per-plugin settings live under `AppSettings.plugin_settings` keyed by plugin ID

DataLens also supports *metadata overrides* for discovered plugins (without
editing plugin manifests on disk):

- Stored in `AppSettings.plugin_overrides`
- Used to override fields like author/description/group/nav label for UI/UX
  purposes
- Edited via `Plugins -> Manage Plugins…`

## Built-in app fields

`AppSettings` also stores a few core app fields used by the welcome/startup UX:

- `last_project_root`: last selected project folder (used for `--skip-welcome` + “load last project”)
- `recent_projects`: most recently opened project folders (used to populate the welcome “recents” list)
- `welcome_splitter_state_b64`: legacy/temporary (deprecated) welcome UI state field (do not use for new UI persistence)

UI state note:

- UI geometry/layout state (window sizes, splitters, docks) is persisted via Qt `QSettings` (see `datalens.ui.qt_settings`)
  for lower overhead and better native integration.

## App scope vs project scope

As a rule of thumb:

- App/user scoped semantic state belongs in `settings.json` (user data dir): recent projects, enabled plugins, profiles.
- App/user scoped UI layout state belongs in `QSettings`: geometry, splitters, docks.
- Project scoped state belongs in `<project>/.datalens/project.sqlite`: per-project plugin state, project UI layout.

## Updating settings safely

Use the settings helpers so updates are atomic (load → replace → save) and safe
to call from background threads:

For plugin-defined preferences (schema-driven, shown in Preferences → Plugins), see `plugins/preferences.md`.

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
