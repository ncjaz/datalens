---
orphan: true
---

# Sharing between plugins: Events vs Capabilities vs Commands

DataLens V2 has three intentional sharing mechanisms. This page is the "how to use it" guide and the
convergence point for naming.

## Summary (when to use what)

- **Events**: notification only — “X happened”.
  - Don’t treat events as a data pipe.
  - Payloads should be small (IDs, paths, metadata).
- **Capabilities**: pull/query — “give me the current X” or “here is a provider for X”.
  - A capability can be optional (provider plugin disabled/offline).
  - Consumers should degrade gracefully.
- **Commands**: request/response — “please do X for me”.
  - Runs off the UI thread by default (threadpool).
  - Don’t block the UI thread waiting for a result.

High-rate payloads (frames, point streams, etc.) should not be events; use the streaming patterns described in {doc}`streaming`.

## Naming conventions (important)

Treat IDs as API:

- **Core/host reserved namespace**: `datalens.*`
- **Plugin-defined namespace**: `<plugin_id>.*` (recommended)

Avoid inventing multiple strings for the same concept — prefer reusing or extending a shared ID.

### Canonical IDs (stable-ish)

These constants live in `datalens.api.plugins` (also re-exported from `datalens.api.sharing`):

- Implemented:
  - `CAP_WORKSPACE_STATE_SNAPSHOT` = `datalens.workspace_state.snapshot`
  - `CAP_PROJECT_STATUS` = `datalens.project.status`
- Reserved/planned:
  - `CAP_MEDIA_CURRENT` = `datalens.media.current`
  - `CAP_ANNOTATIONS_CURRENT` = `datalens.annotations.current`
  - `CMD_PROJECT_OPEN` = `datalens.project.open`
  - `CMD_PROJECT_CLOSE` = `datalens.project.close`
  - `CMD_WORKSPACE_FOCUS` = `datalens.workspace.focus`

If an ID is marked reserved/planned, don’t rely on it at runtime yet.

## Capabilities: provider + consumer

Provider (plugin `on_app_loaded` / `on_load`):

```python
from datalens.api.plugins import CapabilityProvider

ctx.app.capabilities.register(
    CapabilityProvider(
        capability_id="my_plugin.live_source",
        provider=my_live_source,
        owner_plugin_id=self.plugin_id,
        description="Live camera frames provider.",
    ),
    replace_owner=True,
)
```

Consumer:

```python
live = ctx.app.capabilities.get("my_plugin.live_source")
if live is None:
    return  # provider disabled/offline
frame = live.get_latest()
```

### Core-provided capabilities

Core registers a small set of app-wide providers. Example:

```python
from datalens.api.plugins import CAP_PROJECT_STATUS

status = ctx.app.capabilities.get(CAP_PROJECT_STATUS)
```

## Commands: handler + dispatch

Register a handler:

```python
from datalens.api.plugins import RegisteredHandler

ctx.app.commands.register(
    RegisteredHandler(
        command_id="my_plugin.echo",
        handler=lambda cmd: {"echo": cmd.payload},
        owner_plugin_id=self.plugin_id,
    ),
    replace=True,
)
```

Dispatch (don’t block UI on `.result()`):

```python
future = ctx.app.commands.dispatch("my_plugin.echo", {"hello": "world"})
future.add_done_callback(lambda f: print(f.result()))
```

## Events: publish + subscribe

Events are for “something changed”, not “here’s a big payload”.

Subscribe:

```python
from datalens.api.plugins import EventHub

def on_project_changed(payload) -> None:
    ...

sub = ctx.app.events.subscribe(EventHub.ACTIVE_PROJECT_CHANGED, on_project_changed)
```

Publish (any thread is allowed; delivery is queued to the UI thread):

```python
ctx.app.events.publish("MyEventName", {"id": 123})
```

## Don’t touch Qt off-thread

Capabilities/commands/events are designed to keep the UI responsive. The hard rule still applies:

**Never touch Qt widgets from a background thread.**

See {doc}`stability` for the canonical snippet.

