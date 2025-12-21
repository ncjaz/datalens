# Creating plugins

This page captures the recommended V2 plugin shape so we can keep plugins
consistent, make them easy to maintain, and eventually auto-generate a plugin
skeleton via a "Create plugin..." workflow.

## Goals

- Plugins are optional and isolated (no plugin-to-plugin imports).
- Plugins integrate via stable contracts (domain types + runtime interfaces).
- Plugins can contribute:
  - a workspace UI
  - a Preferences/Config page
  - background services
  - capabilities (shared providers) + commands (requests)
  - project persistence (tables/kv) via the project database API

## Suggested plugin folder layout

V2 plugins live under the `datalens/plugins/` folder.

- Shipped plugins (bundled with the app): `datalens/plugins/<plugin_id>/` (or nested under a pack)
- User-installed plugins: `<user data dir>/plugins/<plugin_id>/` (or nested under a pack)

To support "packs", the loader discovers plugins recursively. Any folder that
contains a `manifest.json` is treated as a plugin root:

- `datalens/plugins/<pack>/<plugin_id>/manifest.json`
- `<user data dir>/plugins/<pack>/<plugin_id>/manifest.json`

A plugin root typically contains:

- `manifest.json`: metadata used by the loader + welcome UI
  - `id`, display name, description, group
  - `stage` (`dev`/`alpha`/`beta`/`release`)
  - dependencies (`requirements.txt` + optional "manual" requirements)
  - what the plugin provides (workspaces, config pages, capabilities, commands)
- `plugin.py`: runtime entrypoint (the host loads this for enabled plugins)
  - export `PLUGIN` or `get_plugin()`
  - implement lifecycle hooks (`on_load`, `on_project_migrate`, `on_project_opened`, `on_project_closing`)
- `ui/` (WORKSPACE plugins): workspace widgets/panels
- `services/` (SERVICE/DATASOURCE/MODEL plugins): non-UI logic and background orchestration
- `requirements.txt` (optional): pip install specifiers for this plugin
- `manual_requirements.md` (optional): deps users must install themselves (e.g. PyTorch)

Note: V2 does not auto-install plugin requirements yet; `requirements.txt` is
currently used for display/diagnostics only.

## Runtime contracts (what the app provides)

These are runtime/application layer concepts (not domain):

Prefer importing runtime contracts from `datalens.api.plugins` so plugins don’t
churn as V2 evolves.

- `ProjectAwarePlugin`: convenience base class with safe project gating
  - app hooks: `on_app_loaded` / `on_app_unloaded`
  - project hooks: `on_project_migrate` / `on_project_ready` / `on_project_teardown`
  - focus hooks: `on_focus` / `on_defocus` (workspace plugins)
- `PluginAppContext` / `PluginProjectContext`: injected by the host
  - capability registry + command bus
  - (when a project is open) access to the project DB via `ctx.db` (PluginDb)

## Preferences (Edit → Preferences)

The host app owns a single Preferences window with a left navigation.

- Core pages: theme, shortcuts, etc.
- Pages are namespaced by plugin (e.g. "Capture", "Annotation") so plugins do
  not need to know about other plugins.

## Create plugin workflow

DataLens includes a **Create New Plugin** workflow that scaffolds a plugin folder
under the user plugins directory. The generated structure depends on the plugin
kind:

- WORKSPACE: generates `manifest.json`, `plugin.py`, and a minimal `ui/` stub.
- SERVICE/DATASOURCE/MODEL: generates `manifest.json`, `plugin.py`, and a minimal `services/` stub.

The scaffolded `plugin.py` includes docstrings explaining each lifecycle hook so
plugin authors can use it as a reference.

## Threading rule (non-negotiable)

Plugins must never touch Qt widgets from non-UI threads.

- Plugin hooks are frequently invoked from background loader stages.
- Marshal UI updates back to Qt (signals or `QTimer.singleShot(0, ...)`).

## Project DB migrations (plugin-owned tables)

Plugins may create/migrate **their own** SQLite tables when a project opens.
Core runs core DB migrations first, then invokes enabled plugins' `on_project_migrate` hooks.

Recommended approach:

- Create as many plugin-owned tables as needed (namespaced by `plugin_id`).
- Track plugin schema versions using the core-owned `plugin_meta` row for your plugin.
- Prefer stable schemas and version **data** via ids/columns (not a new table per data version).

Helper (optional):

- `datalens.services.db.plugin_migrations.run_plugin_migrations(...)` runs versioned migrations on the DB executor thread and updates `plugin_meta`.
