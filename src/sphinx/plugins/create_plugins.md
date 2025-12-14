# Creating plugins

This page captures the recommended V2 plugin shape so we can keep plugins
consistent, make them easy to maintain, and eventually auto-generate a plugin
skeleton via a “Create plugin…” workflow.

## Goals

- Plugins are optional and isolated (no plugin-to-plugin imports).
- Plugins integrate via stable contracts (domain types + runtime interfaces).
- Plugins can contribute:
  - a workspace/tab UI
  - a Preferences/Config page
  - background services
  - capabilities (shared providers) + commands (requests)
  - project persistence (tables/kv) via the project database API

## Suggested plugin folder layout

V2 plugins live under `datalens/services/plugins/<plugin_id>/`:

- `manifest.py` (or future `manifest.json`): metadata used by the loader + welcome UI
  - `plugin_id`, display name, description, group, kind
  - dependencies (`requirements.txt` + optional “manual” requirements)
  - what the plugin provides (tabs, config pages, capabilities, commands)
- `plugin.py`: runtime entrypoint (the loader instantiates this)
- `tabs/` (optional): workspace UI(s)
  - `main_tab.py` (or multiple tabs if the plugin provides more than one)
- `config/` (optional): Preferences/Settings UI integration
  - `config_page.py`: defines the plugin’s config section under Edit → Preferences
- `persistence/` (optional): project persistence integration
  - `migrations/`: schema migrations owned by the plugin
  - `repo.py`: repository helpers over the project DB API (plugin tables / KV)
- `requirements.txt` (optional): pip install specifiers for this plugin
- `manual_requirements.md` (optional): deps users must install themselves (e.g. PyTorch)

## Runtime contracts (what the app provides)

These are runtime/application layer concepts (not domain):

- `BasePlugin`: plugin lifecycle + discovery surface
  - required `plugin_id`
  - declares what it provides (tabs/config pages/capabilities/commands)
- `PluginContext`: injected by the app
  - access to theme, event hub, settings access, capability registry, command bus
  - (when a project is open) access to the project DB and project services
- `ConfigPage`: plugin config section
  - `id`, `title` (and optional icon)
  - `create_widget(parent, ctx) -> QWidget`

## Preferences (Edit → Preferences)

The host app owns a single Preferences window with a left navigation.

- Core pages: theme, shortcuts, etc.
- Plugin pages: discovered via `plugin.get_config_pages()`
- Pages are namespaced by plugin (e.g. “Capture”, “Annotation”) so plugins do
  not need to know about other plugins.

## Planned “Create plugin…” generator

The skeleton generator should create at minimum:

- `manifest.py` with a stable `plugin_id`
- `plugin.py` that registers:
  - a placeholder tab (optional)
  - an empty config page (optional)
- `requirements.txt` template
- `manual_requirements.md` template

And it should ensure the plugin appears on the welcome screen (via manifest
discovery), with a placeholder config page in Preferences.

