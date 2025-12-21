# Plugin lifecycle

The plugin runtime owns plugin lifetimes and keeps the UI consistent when
features are enabled/disabled.

Implementation:

- Runtime coordinator: `datalens.services.plugins.runtime.host.PluginHost`
- Hook interfaces: `datalens.services.plugins.runtime.contracts`

## Phases

1. **Discover**: locate plugin definitions (shipped + external).
2. **Load**: import the plugin runtime entrypoint (`plugin.py`) for enabled plugins.
3. **Enable**: run `on_load(...)` and register features, capabilities, and command handlers.
4. **Activate**: (UI) create tabs lazily when selected; (services) start workers.
5. **Disable**: unregister capabilities/handlers and stop background work.

## Enable/disable policy (today)

V2 currently treats enable/disable as **persisted state**:

- the Manage Plugins UI edits `settings.json` (`enabled_plugins`)
- changes apply on next startup / next project-open enable stage

True “hot enable/disable” while the app is running is possible in-process, but
it is not a user-facing workflow yet. Treat it as internal plumbing until the
UX + lifecycle edge-cases are fully hardened.

## Runtime entrypoint (`plugin.py`)

Each plugin root may include a `plugin.py` file. When the user enables a plugin,
the host loads this file and creates a plugin runtime instance.

Contract:

- `plugin.py` must export either:
  - `PLUGIN` (an instance), or
  - `get_plugin()` (factory returning an instance)
- the instance must expose `plugin_id` matching the manifest `id`

Lifecycle hooks:

- `on_load(app_ctx)` runs when the plugin is enabled for this app run
- `on_project_opened(project_ctx)` runs after a project is opened/attached
- `on_project_closing(project_ctx)` runs during project close, before core closes `ProjectDb`/`IoWriter`

For shutdown correctness, plugins should flush pending work via these hooks.
The host invokes them through the shared flush hook mechanism
(`AppContext.register_project_flush_hook`).

## UI tabs

Tabs should be created lazily and should not assume that other plugins are
available. If a dependency capability is missing, the tab should:

- disable the relevant UI controls, and/or
- offer an “enable provider” action (via the command bus).

## Threading rule (non-negotiable)

Do not access Qt widgets from non-UI threads. Plugin hooks often run in
background loader stages.

If you need to update UI, marshal back to the Qt thread (signals or
`QTimer.singleShot(0, ...)`).
