# Plugin overview

V2 plugins are **optional**, **isolated** feature packages that integrate with
the host application through stable contracts (domain types + plugin runtime
interfaces).

## Goals

- Allow features to be enabled/disabled independently.
- Avoid plugin-to-plugin imports (keep boundaries clean).
- Support “provider might be offline” gracefully.
- Enable shared systems (e.g., live camera feed) to be consumed by multiple tabs.

## Where plugins live

Plugins are discovered recursively from two roots:

- `datalens/plugins/` (shipped plugins, optionally organised into packs/subfolders)
- `<user data dir>/plugins/` (user-installed plugins, optionally organised into packs/subfolders)

A folder is treated as a plugin root if it contains a `manifest.json`.

## What a plugin can provide

Common plugin feature kinds:

- **Workspace**: a user-facing UI surface (e.g., Capture, Review, MEval).
- **Service**: background logic (indexing, syncing, watchers).
- **Data source**: a storage backend or remote API provider.
- **Model**: model families/variants and runtime wiring.

## Rules

- Plugins should depend on **core/domain contracts**, not other plugins.
- Shared resources should be exposed as **capabilities** (data/services), not by
  handing out internal widgets.
- Cross-plugin requests should go through the **command bus** (request/response),
  not direct method calls.

## Stable imports

Plugin code should prefer importing from `datalens.api.plugins`:

```python
from datalens.api.plugins import ProjectAwarePlugin, PluginAppContext, PluginProjectContext
```

This keeps plugins insulated from internal module reshuffles as V2 evolves.
