# State registry + inspector (V2 plan)

Objective
---------

Provide a lightweight, queryable "current state" surface so:

- newly enabled plugins can sync immediately (no event replay needed),
- core and plugins can coordinate on a few well-known concepts (project, active item),
- developers/users can inspect current core/plugin state via a read-only UI.

This is **not** a replacement for:

- the planned EventHub (events are for change notifications),
- persistent settings (`settings.json` / `QSettings`),
- streaming/ring-buffer APIs for high-rate payloads.

Scope
-----

- Add a **typed core state service** for a small set of well-known state.
- Add a **namespaced plugin state registry** (dict-like, but scoped to plugin id).
- Add a **read-only inspector UI** under **Help -> States**.

Non-goals
---------

- No “global dict of everything” owned by everyone.
- No high-rate payloads (frames, arrays) in the state registry.
- No automatic persistence of the state registry (except where explicitly defined).

Design
------

### 1) Core state: `WorkspaceStateService`

This is a small, typed service owned by core. It answers "what is the current value right now?"

Proposed fields (initial):

- `project_root: Path | None`
- `active_workspace_id: str | None`
- `active_item_id: str | None` (e.g. current image id/path token)

API sketch:

- `get_snapshot() -> WorkspaceStateSnapshot` (dataclass, JSON-serializable)
- `set_active_item_id(value, source=...)` (updates state + emits change notification)
- `set_active_workspace_id(value, source=...)`

Where it lives:

- `datalens/services/workspace_state_service.py` (application/service layer)
- `datalens/domain/system/workspace_state.py` (pure dataclasses for snapshot/payload types)

Change notifications:

- Publish via the planned EventHub (or a minimal interim signal/callback list):
  - `workspace.active_item_changed`
  - `workspace.active_workspace_changed`
  - `workspace.project_changed`

### 2) Plugin state: `PluginStateRegistry`

This enables late joiners and debugging by providing a queryable, namespaced state store.

Rules:

- Keys are namespaced by plugin id: `plugins/<plugin_id>/<key>`
- Plugins may **write only their own** namespace.
- Other plugins may read (explicitly "read-only cross-plugin").
- Values must be JSON-serializable (or dataclass -> dict).
- State entries track a `updated_at` (monotonic/time).

API sketch:

- `set(plugin_id, key, value)` (write scoped)
- `get(plugin_id, key) -> value | None`
- `list(plugin_id) -> dict[key, entry]`
- `snapshot() -> PluginStateSnapshot` (for inspector)

Where it lives:

- `datalens/services/plugin_state_registry.py`
- Domain types: `datalens/domain/system/plugin_state.py` (dataclasses)

### 3) Inspector UI: Help -> States

Goal: a lightweight, read-only view of current core + plugin state for debugging and support.

UI requirements:

- Accessible via **Help -> States**
- Read-only (no edits)
- Two sections:
  - **Core**: shows `WorkspaceStateService` snapshot
  - **Plugins**: shows `PluginStateRegistry` snapshot (grouped by plugin id)
- Updates:
  - Prefer "push on change" (EventHub notifications).
  - Fallback to a low-rate refresh timer (e.g. 250-500ms) only if needed.
- Must not block UI thread (any expensive formatting must be minimal).

Where it lives:

- Menu action: `datalens/ui/menus/help/menu.py` + `datalens/ui/menus/help/controller.py`
- Dialog: `datalens/ui/menus/help/states/states_dialog.py`

Correctness criteria
--------------------

- Late-enabled plugins can always query core state and sync on load.
- Plugin state writes are scoped to plugin id via the registry API.
- Inspector never blocks the UI thread (no file IO, no DB calls).
- State snapshots are stable and JSON-serializable.

Failure modes
-------------

- If a plugin publishes invalid (non-serializable) state:
  - registry rejects with a clear exception and logs the plugin id + key.
- If inspector cannot render a value:
  - render a placeholder string and continue; never crash the app.

Performance constraints
-----------------------

- State updates are low-rate (human-scale). Anything high-rate belongs in streaming.
- Avoid per-frame UI refresh; use event-driven updates or coarse polling.

Implementation tasks (ordered)
------------------------------

1. Add domain dataclasses: `WorkspaceStateSnapshot`, `PluginStateEntry`, `PluginStateSnapshot`.
2. Implement `WorkspaceStateService` (core-owned).
3. Implement `PluginStateRegistry` (namespaced, scoped writes).
4. Wire service instances into `AppContext` (or a dedicated service container).
5. Add Help -> States menu item (shows inspector dialog).
6. Implement inspector dialog UI (core + plugin sections).
7. Document the contract for plugin authors (what to store, how to namespace keys).

Status
------

- Design: planned
- Implementation: not started
