# Plugin Preferences System (Plan)

## Objective

Add a **Plugins** root section in the Preferences dialog where each plugin can expose **semantic, persisted preferences**
(toggles, dropdowns, numeric values, paths) that:

- are stored in `settings.json` (app/user scoped) and survive restarts
- can be shown/edited **even when a plugin is disabled** (no runtime import required)
- are easy for plugin developers to define
- are safe for the UI thread (no blocking I/O)
- can be observed as **state** (for the “States” inspector UI and for plugins/services that want to react to changes)

## Non-goals (v0)

- Hot-loading/unloading plugins based on preference changes (separate lifecycle work).
- Arbitrary custom Qt widgets for preferences (v0 is schema-driven; custom pages may be added later).
- “Secure sandboxing” of plugin preferences (plugins can still bypass our APIs if they choose; this is a correctness contract).

## What We Already Have

### Persistence primitives (app/user scoped)

- `AppSettings.plugin_settings: Mapping[str, Mapping[str, object]]`
  - file: `datalens/src/datalens/domain/system/settings.py`
  - intended to store plugin-owned settings under `plugin_settings[plugin_id][key]`
- Thread-safe, atomic persistence:
  - `SettingsStore` and `DebouncedSettingsWriter`
  - files: `datalens/src/datalens/services/settings_store.py`, `datalens/src/datalens/core/app_settings.py`

### Preferences UI framework

- Preferences dialog supports “root + children” navigation pages already.
  - file: `datalens/src/datalens/ui/menus/edit/preferences/preferences_dialog.py`

### State/inspection UI

- “States” dialog exists and can show app/plugin state snapshots.
  - file: `datalens/src/datalens/ui/menus/help/states/states_dialog.py`
- `WorkspaceStateService` already exists and stores structured runtime state.
  - file: `datalens/src/datalens/services/workspace_state_service.py`

## What’s Missing (v0 requirements)

1) A plugin-facing **settings API** (so plugins don’t hand-roll JSON merging and file writes).
2) A **change notification** mechanism so:
   - the Preferences UI can update live
   - plugins can react to preference changes without polling
   - the “States” UI can show current effective preferences
3) A **schema format** that allows:
   - building the Preferences UI without importing plugin runtime code
   - validation / defaults
   - stable naming and organization (sections, ordering, help text)
4) A Preferences UI implementation for:
   - root: **Plugins**
   - children: one page per discovered plugin
   - auto-built controls from schema

## Core Design Decisions

### A) Preferences are persisted configuration (not “live state”)

- **Preferences** are persisted values under `settings.json`.
- **State** is runtime snapshot data (“what’s happening right now”).

However: the system should **surface preferences into state** so:

- the “States” UI can show the effective values
- plugins can query current preferences without constantly reading disk

### B) Schema-driven for disabled plugins

If a plugin is disabled, we still want to show/edit its preferences without importing it. Therefore:

- the schema must be readable from **metadata-only discovery**
- recommended location:
  - inside `manifest.json` (under a `preferences` key), or
  - a sidecar `preferences.json` referenced from the manifest

### C) UI-thread safety

- Preferences UI must never write to disk synchronously on the UI thread.
- All writes go through `DebouncedSettingsWriter` (background thread, coalesced).
- Reads should be cached in-memory and refreshed via events.

### D) Single source of truth for snapshots (avoid drift)

To avoid maintaining multiple competing “snapshots” of preferences:

- `PluginPreferencesService.snapshot()` is the **single source of truth** for a JSON-serializable view of preferences.
- The “States” inspector should display this snapshot (either directly or via `WorkspaceStateService` embedding it).
- Any capability provider must call the same snapshot function (no duplicate formatting logic).

## Proposed Architecture (v0)

### New service: `PluginPreferencesService`

Add a small service that wraps `SettingsStore` + `DebouncedSettingsWriter` and exposes:

- `get_plugin(plugin_id) -> PluginPreferences`
- `get(plugin_id, key, default) -> object`
- `set(plugin_id, key, value) -> None` (debounced write)
- `replace(plugin_id, mapping) -> None` (debounced write)
- `subscribe(plugin_id, callback) -> unsubscribe` (UI-friendly; callback runs on UI thread via EventHub delivery)
- `snapshot() -> dict` (for States UI and diagnostics)

Implementation notes:

- Keep an **in-memory cache** of the last loaded `AppSettings` (or just `plugin_settings`) to avoid repeated disk reads.
- On `set/replace`, update cache immediately and publish a `PluginPreferencesChanged` event.
- Periodic disk flush is handled by `DebouncedSettingsWriter`; on app exit, ensure a final flush runs (already handled by current shutdown path).

### Events

Publish events via the existing `EventHub`:

- `EventHub.PLUGIN_PREFERENCES_CHANGED`
  - payload: `PluginPreferencesChanged(plugin_id, changed_keys, timestamp_s)`

Logging expectations:

- `debug`: when publishing and delivering to subscribers (rate-limit if needed)
- `info`: only for user-visible transitions (e.g., “Preferences applied” is UI-level; not per-key)

### State integration

Update `WorkspaceStateService.snapshot()` (or an equivalent root snapshot) to include:

- `preferences.plugins.<plugin_id>.<key> = value`

This gives:

- “States” UI: shows preferences as part of the state tree
- Plugins/services: can query `workspace_state.snapshot()` for diagnostics and effective values (without disk access)

Important:

- Treat this as a **view** of preferences, not the source of truth.
- The source remains `settings.json` via the service cache.

### Capability (optional but recommended)

Provide a capability so plugins can query preferences without importing any UI layer:

- `capability_id = "datalens.plugin_preferences.snapshot"`
- provider: `PluginPreferencesService.snapshot`

Implemented in core as `CAP_PLUGIN_PREFERENCES_SNAPSHOT = "datalens.plugin_preferences.snapshot"`.

This is useful for:

- plugin diagnostics panels
- scripts/tools
- future IPC or external inspection

## UI: Preferences → Plugins

### Navigation

Add root: **Plugins**

Children pages:

- One page per discovered plugin (from the plugin registry metadata).
- Order: by plugin group, then by display name.

### Auto-built forms

From schema → build controls:

Supported field kinds (v0):

- `bool` → `DatalensCheckBox`
- `enum` → `QComboBox` (with display labels)
- `toggle` → `Toggle` (2–3 options; falls back to `QComboBox` if needed)
- `int`/`float` → `QSpinBox` / `QDoubleSpinBox`
- `string` → `QLineEdit`
- `path` (file/dir) → `QLineEdit` + browse button + "Open in Explorer/Finder" button where relevant

UI constraints:

- Use global QSS + DataLens widgets where available (`DatalensButton`, `DatalensCheckBox`, `Toggle`).
- Writes are debounced; UI updates are immediate.

### Schema format (v0, implemented)

Minimal manifest extension example:

```json
{
  "id": "capture",
  "name": "Capture",
  "preferences": {
    "schema_version": 1,
    "title": "Capture",
    "sections": [
      {
        "id": "devices",
        "title": "Devices",
        "fields": [
          {
            "key": "auto_refresh_modifier",
            "title": "Auto-refresh modifier",
            "kind": "enum",
            "options": [
              { "id": "shift", "label": "Shift" },
              { "id": "ctrl", "label": "Ctrl" },
              { "id": "alt", "label": "Alt" },
              { "id": "meta", "label": "Meta" }
            ],
            "default": "shift",
            "description": "Modifier used for toggling continuous device refresh."
          }
        ]
      }
    ]
  }
}
```

Rules (v0):

- `schema_version` is the schema version number stored in the plugin manifest.
- `key` is the persisted key under `plugin_settings[plugin_id][key]`.
- Schema is **static metadata**; it must not require importing plugin runtime code.

### Schema representation (v0)

We will represent the schema using **dataclasses**, but keep the on-disk format **JSON-only**:

- The manifest/sidecar schema uses plain JSON types only (`str/int/float/bool/null/list/object`).
- Schema dataclasses provide `to_dict()` / `from_dict()` (or module helpers) for conversion.
- No Qt types, no threads, no file I/O in the schema layer.

### Validation

- Clamp/validate values at the service layer when possible (type checks, allowed enums).
- UI should fall back to defaults if stored values are missing/invalid.
- Invalid values should log at `warning` (once per key per session, avoid log spam).

## Plugin Developer Workflow

### Defining preferences

- Add `preferences` schema to `manifest.json` (or `preferences.json` sidecar referenced by manifest).
- Use stable keys; do not rename keys lightly (would orphan user settings).

### Reading/writing preferences at runtime

Plugins should use `ctx.app.preferences` (service) instead of touching `SettingsStore` directly.

Examples:

- Read:
  - `ctx.app.preferences.get(plugin_id, "auto_refresh_modifier", default="shift")`
- Subscribe:
  - `unsubscribe = ctx.app.preferences.subscribe(plugin_id, callback)`

Important: callbacks must be fast and offload heavy work to background systems.

## Performance and “Don’t Block the GUI”

Potential pitfalls:

- Building a huge preferences form could be expensive if we eagerly create pages for every plugin.
  - Mitigation: lazy-build plugin pages only when selected.
- Excessive event publishing when users drag sliders or type rapidly.
  - Mitigation: debounce writes and rate-limit event logs.
- Re-reading `settings.json` on every toggle.
  - Mitigation: keep an in-memory cache and publish changes from the cache.

## Task Breakdown (Implementation Plan)

1) **Domain schema**
   - Add a small set of domain dataclasses for preference schemas (field specs, sections).
   - Keep them Qt-free and JSON-serializable.
   - Add `to_dict()` / `from_dict()` helpers for schema dataclasses (v0 only; avoid a global base-class framework).

2) **Service**
   - Implement `PluginPreferencesService`:
     - cache + debounced writes
     - publish `PluginPreferencesChanged`
     - `snapshot()`

3) **EventHub integration**
   - Add event id + payload dataclass.
   - Add debug logging for publish/deliver (rate-limited).

4) **WorkspaceState integration**
   - Add preferences snapshot into the state tree.
   - Ensure state snapshot is cheap (no disk I/O).

5) **Preferences UI**
   - Add root “Plugins”
   - Add per-plugin child pages (lazy)
   - Auto-build widgets from schema
   - Wire controls to service (debounced write, immediate UI reflect)

6) **Docs**
   - Add a Sphinx page under Plugins or Core Systems describing:
     - schema format
     - persistence model
     - “preferences vs state”
     - examples

## Correctness Criteria (v0)

- Preferences can be viewed/edited for a disabled plugin (metadata-only).
- Changes persist to `settings.json` without blocking the UI thread.
- Plugins can read preferences and subscribe to changes.
- The "States" inspector shows current effective plugin preferences.
- No crashes without logs; failures are best-effort and logged with tracebacks.

## Improvements and Additions to Plan

### 1. Schema Enhancement: Support for Toggle Widget

**Current issue**: The capture plugin uses a 2-button `Toggle` widget for "Manual/Auto" scan mode, which provides better UX than a dropdown for binary/tertiary choices. The current schema only supports `enum` → `QComboBox`.

**Proposal**: Add `toggle` field kind to the schema:

```json
{
  "key": "scan_mode",
  "title": "Default scan mode",
  "kind": "toggle",
  "options": [
    {"id": "manual", "label": "Manual"},
    {"id": "auto", "label": "Auto"}
  ],
  "default": "manual",
  "description": "Controls startup behavior for device scanning."
}
```

**Implementation**:
- `kind: "toggle"` with 2 options → `Toggle` widget
- `kind: "toggle"` with 3+ options → fallback to `QComboBox` with warning
- Add validation in schema parser to ensure `options` has 2-4 entries with `id` and `label`

**Benefits**:
- Better UX for binary/tertiary choices (Manual/Auto, Local/Global/Project)
- Consistent with existing DataLens V2 design patterns
- Preserves dropdown for 4+ choices where Toggle becomes cluttered

### 2. Migration Path for Existing Ad-Hoc Preferences

**Current issue**: The capture plugin already has ad-hoc preferences implemented:
- `auto_refresh_modifier` (stored, loaded, but managed manually)
- `scan_mode` (stored, loaded, but managed manually)
- Direct calls to `SettingsStore` and `DebouncedSettingsWriter`

**Proposal**: Add migration guidance to the plan:

**Step 1: Add schema to manifest (non-breaking)**
- Plugin continues to use old API during transition
- Preferences UI can show/edit values even before plugin migrates runtime code

**Step 2: Migrate runtime code to service API**
- Replace manual `_load_user_preferences()` / `_save_user_preference()` with:
  - `ctx.app.preferences.get(plugin_id, key, default)`
  - `ctx.app.preferences.set(plugin_id, key, value)`
- Subscribe to changes via `ctx.app.preferences.subscribe(plugin_id, callback)`

**Step 3: Remove manual persistence code**
- Delete `_load_user_preferences()`, `_save_user_preference()`, and mutator functions
- Rely entirely on service API

**Backward compatibility**:
- Service should read existing `plugin_settings[plugin_id][key]` values from disk
- No data loss during migration (keys remain the same)
- Old and new code can coexist temporarily

### 3. Workspace-Scoped vs App-Scoped Preferences

**Current gap**: The plan only covers app-scoped preferences (global, stored in `settings.json`).

**Real-world use case**:
- **App-scoped**: "Default scan mode" (user's preferred startup behavior across all projects)
- **Workspace-scoped**: "Last selected camera for this project" (project-specific, should persist per workspace)

**Proposal**: Extend the system to support both scopes:

**Schema annotation**:
```json
{
  "key": "scan_mode",
  "title": "Default scan mode",
  "kind": "toggle",
  "scope": "app",  // NEW: "app" (default) or "workspace"
  "options": [...]
}
```

**Service API**:
```python
# App-scoped (current plan)
ctx.app.preferences.get(plugin_id, key, default)

# Workspace-scoped (new)
ctx.workspace.preferences.get(plugin_id, key, default)
```

**Storage**:
- App-scoped: `settings.json` (user home directory)
- Workspace-scoped: `.datalens/workspace_settings.json` (project directory)

**Preferences UI**:
- App-scoped preferences: shown in global Preferences dialog
- Workspace-scoped preferences: shown in Workspace Settings (new dialog) or inline in workspace UI
- Clear visual distinction (e.g., icon or label indicating scope)

**v0 decision**: Implement app-scoped only. Add workspace-scoped in v1 if needed.

### 4. Field-Level Visibility and Enablement Rules

**Current gap**: No support for conditional fields (e.g., "Show field X only if field Y is set to Z").

**Common patterns**:
- Show "Auto-refresh interval" only when scan mode is "Auto"
- Enable "Save depth" only for RealSense devices, disable for webcams

**Proposal**: Add optional `visible_when` and `enabled_when` rules to schema:

```json
{
  "key": "auto_refresh_interval_ms",
  "title": "Auto-refresh interval (ms)",
  "kind": "int",
  "default": 2500,
  "visible_when": {"scan_mode": "auto"},  // Only show when scan_mode == "auto"
  "description": "How often to refresh device list in auto mode."
}
```

**Implementation**:
- Simple equality checks only in v0 (no complex expressions)
- UI listens to preference changes and shows/hides/enables/disables fields reactively
- Missing/hidden fields still have defaults and can be set programmatically

**v0 decision**: Skip this for v0. Add in v1 if plugin developers request it. For now, plugins can show all fields unconditionally.

### 5. Validation and Constraints

**Current gap**: Schema has `default` but no way to specify ranges, regex, or custom validation.

**Proposal**: Add optional validation constraints:

```json
{
  "key": "auto_refresh_interval_ms",
  "title": "Auto-refresh interval (ms)",
  "kind": "int",
  "default": 2500,
  "min": 500,      // NEW: Minimum value
  "max": 10000,    // NEW: Maximum value
  "step": 100,     // NEW: Increment for spinbox
  "description": "How often to refresh device list."
}
```

**For strings**:
```json
{
  "key": "device_filter",
  "title": "Device name filter",
  "kind": "string",
  "default": "",
  "pattern": "^[a-zA-Z0-9_\\- ]*$",  // NEW: Regex validation
  "description": "Filter devices by name (regex supported)."
}
```

**Behavior**:
- Service validates on `set()` and clamps/rejects invalid values
- UI reflects constraints (spinbox min/max, input validation)
- Log warnings for invalid values with actionable error messages

**v0 decision**: Implement `min`, `max`, `step` for numeric types. Skip `pattern` for v0 (can add in v1).

### 6. Preferences Reset to Defaults

**Current gap**: No way for users to reset preferences to defaults.

**Proposal**: Add UI affordance in Preferences dialog:

**Per-plugin reset**:
- "Reset to Defaults" button at top of each plugin's preferences page
- Shows confirmation dialog: "Reset all preferences for [Plugin Name] to defaults?"
- Deletes `plugin_settings[plugin_id]` from disk, reloads schema defaults into UI

**Global reset**:
- "Reset All Plugins" button in root "Plugins" page
- Shows confirmation with list of affected plugins

**Service API**:
```python
ctx.app.preferences.reset(plugin_id)  # Reset one plugin
ctx.app.preferences.reset_all()       # Reset all plugins
```

**v0 decision**: Implement per-plugin reset. Skip global reset (can add later).

### 7. Schema Versioning and Migration

**Current gap**: No plan for handling schema changes over time.

**Common scenarios**:
- Plugin renames a preference key (e.g., `auto_refresh_modifier` → `refresh_modifier`)
- Plugin changes type (e.g., `bool` → `toggle` with 2 options)
- Plugin removes a deprecated preference

**Proposal**: Add optional `schema_version` and `migrations` to manifest:

```json
{
  "id": "capture",
  "preferences": {
    "schema_version": 2,  // NEW: Increment when schema changes
    "migrations": [       // NEW: Transformations for old stored values
      {
        "from_version": 1,
        "to_version": 2,
        "renames": {
          "auto_refresh_modifier": "refresh_modifier"
        },
        "removals": ["deprecated_key"]
      }
    ],
    "sections": [...]
  }
}
```

**Behavior**:
- On first load, service checks stored preferences against current schema version
- Applies migrations sequentially (v1→v2→v3) to bring stored values up to date
- Logs migrations at `info` level
- Saves migrated values back to disk

**v0 decision**: Skip migrations for v0. Plugins should use stable keys and avoid renames. Add migrations in v1 when mature plugins need it.

### 8. Help Text and Documentation Links

**Current gap**: Schema has `description` but no way to link to detailed docs.

**Proposal**: Add optional `help_url` to fields:

```json
{
  "key": "auto_refresh_modifier",
  "title": "Auto-refresh modifier",
  "kind": "enum",
  "options": [
    { "id": "shift", "label": "Shift" },
    { "id": "ctrl", "label": "Ctrl" },
    { "id": "alt", "label": "Alt" },
    { "id": "meta", "label": "Meta" }
  ],
  "default": "shift",
  "description": "Modifier used for toggling continuous device refresh.",
  "help_url": "https://docs.datalens.com/plugins/capture/preferences#auto-refresh"
}
```

**UI**:
- Show small help icon (?) next to field label
- Clicking opens URL in default browser
- Tooltip on hover shows `description`

**v0 decision**: Implement `description` tooltips only. Skip `help_url` for v0 (can add later).

### 9. Grouping and Section Collapsibility

**Current gap**: Sections are shown flat. For plugins with many preferences, this becomes unwieldy.

**Proposal**: Make sections collapsible (QGroupBox with expand/collapse):

```json
{
  "id": "advanced",
  "title": "Advanced",
  "collapsed": true,  // NEW: Start collapsed
  "fields": [...]
}
```

**UI**:
- Sections render as `QGroupBox` with a clickable title bar
- Click to expand/collapse
- State persists in UI (not saved to disk, just session memory)

**v0 decision**: Implement collapsible sections. This is low-cost and high-value for large preference pages.

### 10. Service Initialization and App Context Wiring

**Current gap**: Plan doesn't specify how `PluginPreferencesService` is created and wired into `AppContext`.

**Proposal**: Follow existing service patterns:

**Service creation** (in `datalens/src/datalens/services/preferences/plugin_preferences_service.py`):
```python
class PluginPreferencesService:
    def __init__(
        self,
        settings_store: SettingsStore,
        settings_writer: DebouncedSettingsWriter,
        event_hub: EventHub,
    ):
        self._store = settings_store
        self._writer = settings_writer
        self._events = event_hub
        self._cache: dict[str, dict[str, object]] = {}
        self._load_cache()
```

**Wiring** (in `datalens/src/datalens/core/app_context.py`):
```python
@dataclass
class AppContext:
    # ... existing fields ...
    preferences: PluginPreferencesService  # NEW
```

**Initialization** (in main app startup):
```python
preferences_service = PluginPreferencesService(
    settings_store=default_settings_store(),
    settings_writer=default_debounced_settings_writer(),
    event_hub=event_hub,
)
app_ctx = AppContext(..., preferences=preferences_service)
```

**v0 decision**: Implement this as part of Step 2 (Service implementation).

### 11. Testing Strategy

**Current gap**: No testing plan.

**Proposal**: Add unit and integration tests:

**Unit tests**:
- Schema parsing (valid/invalid manifests)
- Service CRUD operations (get/set/replace)
- Event publishing and subscription
- Validation and clamping

**Integration tests**:
- End-to-end: load plugin with preferences schema → build UI → change value → verify disk write
- Migration test: write old schema values → load with new schema → verify migrated

**Manual testing**:
- Preferences UI with multiple plugins (capture, annotation, etc.)
- Disable a plugin → verify preferences still editable
- Change theme → verify preferences UI updates colors

**v0 decision**: Write unit tests for service and schema. Add integration tests for Preferences UI. Manual test with at least 2 plugins.

### 12. Real-World Example: Capture Plugin Migration

**Current state**: Capture plugin has 2 ad-hoc preferences:
- `auto_refresh_modifier` (enum: shift/ctrl/alt/meta)
- `scan_mode` (toggle: manual/auto)

**Step 1: Add schema to manifest.json**:
```json
{
  "id": "capture",
  "name": "Capture",
  "preferences": {
    "schema_version": 1,
    "sections": [
      {
        "id": "devices",
        "title": "Device Settings",
        "fields": [
          {
            "key": "scan_mode",
            "title": "Default scan mode",
            "kind": "toggle",
            "options": [
              {"id": "manual", "label": "Manual"},
              {"id": "auto", "label": "Auto"}
            ],
            "default": "manual",
            "description": "Controls startup behavior for device scanning."
          },
          {
            "key": "auto_refresh_modifier",
            "title": "Modifier key",
            "kind": "enum",
            "options": [
              {"id": "shift", "label": "Shift"},
              {"id": "ctrl", "label": "Ctrl"},
              {"id": "alt", "label": "Alt"},
              {"id": "meta", "label": "Meta"}
            ],
            "default": "shift",
            "description": "Modifier key used for toggling continuous device refresh."
          }
        ]
      }
    ]
  }
}
```

**Step 2: Migrate runtime code** (replace manual persistence):
```python
# Before (in workspace.py):
def _load_user_preferences(self) -> None:
    settings = self._settings_store.load()
    plugin_settings = settings.plugin_settings.get(_CAPTURE_PLUGIN_SETTINGS_KEY, {})
    self._scan_mode = plugin_settings.get(_SETTING_SCAN_MODE, _DEFAULT_SCAN_MODE)
    # ... manual loading ...

# After:
def _load_user_preferences(self) -> None:
    self._scan_mode = self._app_ctx.preferences.get("capture", "scan_mode", default="manual")
    self._refresh_modifier = self._app_ctx.preferences.get("capture", "auto_refresh_modifier", default="shift")
```

**Step 3: React to changes**:
```python
def __init__(self, ...):
    # Subscribe to preference changes
    self._pref_unsub = self._app_ctx.preferences.subscribe("capture", self._on_preferences_changed)

def _on_preferences_changed(self, changed_keys: set[str]) -> None:
    if "scan_mode" in changed_keys:
        new_mode = self._app_ctx.preferences.get("capture", "scan_mode", default="manual")
        self._apply_scan_mode(new_mode)
    if "auto_refresh_modifier" in changed_keys:
        new_mod = self._app_ctx.preferences.get("capture", "auto_refresh_modifier", default="shift")
        self._apply_refresh_modifier(new_mod)
```

**Benefits of migration**:
- Preferences editable from Preferences dialog (not just in-workspace UI)
- No manual JSON merging code
- Reactive: changes from Preferences dialog instantly update workspace
- Consistent with other plugins

## Updated Task Breakdown (Implementation Plan)

1) **Domain schema** (Enhanced)
   - Add dataclasses for preference schemas (field specs, sections)
   - Support field types: `bool`, `enum`, `toggle`, `int`, `float`, `string`, `path`
   - Add validation constraints: `min`, `max`, `step` for numeric types
   - Add optional `collapsed` flag for sections
   - Keep Qt-free and JSON-serializable

2) **Service** (Enhanced)
   - Implement `PluginPreferencesService`:
     - In-memory cache + debounced writes
     - CRUD: `get()`, `set()`, `replace()`, `reset()`
     - Validation and clamping based on schema
     - Publish `PluginPreferencesChanged` events
     - `snapshot()` for States UI
     - `subscribe()` / `unsubscribe()` for reactive updates
   - Wire into `AppContext` as `ctx.app.preferences`

3) **EventHub integration**
   - Add `PLUGIN_PREFERENCES_CHANGED` event ID + payload dataclass
   - Add debug logging for publish/deliver (rate-limited to avoid spam)

4) **WorkspaceState integration**
   - Add preferences snapshot into state tree: `preferences.plugins.<plugin_id>.*`
   - Ensure snapshot is cheap (read from service cache, no disk I/O)

5) **Preferences UI** (Enhanced)
   - Add root "Plugins" page in Preferences dialog
   - Lazy-build child pages (one per plugin) on selection
   - Auto-build widgets from schema:
     - `bool` → `DatalensCheckBox`
     - `enum` → `QComboBox`
     - `toggle` (2 options) → `Toggle` widget
     - `int`/`float` → `QSpinBox`/`QDoubleSpinBox` with min/max/step
     - `string` → `QLineEdit`
     - `path` → `QLineEdit` + browse button
   - Sections render as collapsible `QGroupBox`
   - "Reset to Defaults" button per plugin
   - Wire controls to service (debounced write on change, immediate UI update)

6) **Migration guide** (New)
   - Document migration path for existing ad-hoc preferences
   - Provide before/after code examples
   - Test migration with capture plugin as reference implementation

7) **Docs** (Enhanced)
   - Add Sphinx page under Plugins describing:
     - Schema format and field types
     - Persistence model (app-scoped vs workspace-scoped for future)
     - "Preferences vs state" conceptual model
     - How to define preferences in manifest.json
     - How to read/write/subscribe at runtime
     - Migration guide from ad-hoc persistence
   - Add capture plugin as worked example

8) **Testing** (New)
   - Unit tests: schema parsing, service CRUD, validation, events
   - Integration tests: end-to-end preference change flow
   - Manual testing: Preferences UI with capture + annotation plugins

## Correctness Criteria (v0 - Updated)

- Preferences can be viewed/edited for a disabled plugin (metadata-only, no runtime import).
- Changes persist to `settings.json` without blocking UI thread (debounced writes).
- Plugins can read preferences via service API and subscribe to changes.
- The "States" inspector shows current effective plugin preferences.
- Toggle widget supported for 2-option fields.
- Numeric fields respect min/max/step constraints.
- Sections are collapsible to reduce UI clutter.
- "Reset to Defaults" works per-plugin.
- Capture plugin successfully migrated from ad-hoc to schema-driven preferences.
- No crashes without logs; failures are best-effort and logged with tracebacks.
