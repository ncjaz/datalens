# Keyboard + Mouse Shortcuts System (V2 plan)

Status: **Planned (not implemented in V2 code yet)**.

## Objective

Implement a first-class shortcut system similar to V1, but extended to support:

- Keyboard chords like `Ctrl+M` and multi-modifier chords like `Ctrl+Shift+M`.
- Mouse input as part of bindings (mouse buttons and wheel), e.g. `Ctrl+LeftClick`, `Alt+WheelUp`.
- Per-window routing: shortcuts should only affect the currently focused window (MainWindow, plugin popouts, dialogs).
- Plugin-friendly registration and configuration UI (plugins can contribute their own page/tab in the shortcuts dialog).
- Conflict prevention within a plugin: a plugin must not bind multiple commands to the same shortcut chord within the same scope.

Non-goals (for the initial implementation):

- OS/global system-wide hotkeys (registered with the OS). We stay inside Qt.
- High-rate input remapping (gaming-style). We focus on productivity shortcuts.

## Constraints (hard requirements)

- **Non-blocking UI**: shortcut dispatch must be fast and must not do I/O or heavy work on the UI thread.
- **Deterministic routing**: only the focused top-level window receives shortcuts.
- **Plugin isolation by convention**: plugins register via the core API; we enforce correctness rules (conflicts) in the registry.
- **No monoliths**: keep UI and logic separate (UI in `datalens/ui/...`, logic in `datalens/services/...`).

## Terms

- **Chord**: a single input gesture with optional modifiers (not a multi-step sequence).
  - Keyboard chord: `Ctrl+Shift+M`
  - Mouse chord: `Ctrl+LeftClick`
  - Wheel chord: `Alt+WheelUp`
- **Command**: a named action, e.g. `"annotate.delete_selection"`.
- **Scope**: where a binding applies (global/app, window, active workspace/plugin).
- **Context**: an enable/disable layer used for priority (active workspace > window > global).

## Design overview

### 1) Core data model (domain)

Add a domain module under `datalens/domain/system/shortcuts.py` with JSON-serializable dataclasses:

- `ShortcutId` (string) and `ShortcutCommandId` (string): stable identifiers.
- `ShortcutScope` enum:
  - `GLOBAL` (app-wide, but still routed only to the focused window)
  - `WINDOW` (only within one top-level window)
  - `WORKSPACE` (only when a given plugin workspace is active/focused)
- `MouseButton` enum: `Left`, `Right`, `Middle`, `Back`, `Forward`.
- `WheelDirection` enum: `Up`, `Down` (optionally `Left/Right` later).
- `KeyboardModifiers` value object (shift/ctrl/alt/meta).
- `InputChord`:
  - `modifiers: KeyboardModifiers`
  - `key: str | None` (Qt key name / `QKeySequence` normalized string)
  - `mouse_button: MouseButton | None`
  - `wheel: WheelDirection | None`
  - Rule: exactly one of `(key, mouse_button, wheel)` is set.
- `ShortcutBinding`:
  - `command_id: str`
  - `chord: InputChord`
  - `mode: ShortcutMode` (planned: `Press`, `Hold`, `Toggle`)

Normalization rules:

- Canonicalize modifier order (`Ctrl+Shift+...`), uppercase letters, and use Qt names for special keys.
- For mouse: canonical strings like `Ctrl+LeftClick`, `Alt+WheelUp`.

### 2) Runtime registry + dispatch (service)

Add `datalens/services/shortcuts/`:

- `ShortcutRegistry` (pure Python, thread-safe, no Qt):
  - Owns registrations: `plugin_id -> ShortcutPageSpec -> command bindings`.
  - Enforces constraints:
    - Within a plugin and a scope, a given `InputChord` maps to at most one command.
    - Within a plugin, `command_id` must be unique.
  - Exposes:
    - `register_page(plugin_id, page_spec) -> handle`
    - `set_binding(plugin_id, command_id, chord, mode)`
    - `list_pages()`, `list_bindings(plugin_id)`
    - conflict reporting for UI (per plugin).

- `ShortcutDispatcher` (Qt-facing, per top-level window):
  - Installs a Qt `eventFilter` on the window (or the application, filtered by `QApplication.activeWindow()`).
  - Converts `QKeyEvent`, `QMouseEvent`, `QWheelEvent` into `InputChord`.
  - Resolves which binding should run based on priority:
    1) Active workspace (focused plugin id) bindings
    2) Window bindings
    3) Global bindings
  - Dispatches by calling a callback registered for `command_id`.

Important routing rules:

- Only dispatch for the currently focused top-level window.
- Do not steal input from text-edit widgets by default:
  - If the focused widget is `QLineEdit/QTextEdit/QPlainTextEdit`, ignore most non-navigation chords unless explicitly marked as allowed for text contexts.

### 3) Plugin integration API

Expose a simple API for plugins in `PluginAppContext`:

- `ctx.app.shortcuts` (new service on `AppContext`)
  - `register_shortcuts(plugin_id, page_spec, callbacks={command_id: callable})`
  - returns a handle with `unregister()` for `on_unload`.

Plugin author workflow:

1) Define shortcuts in one place (page spec: name, sections, entries, defaults).
2) Provide Python callables (callbacks) for each command id.
3) Core registers them in `on_load`.
4) Core disables/enables workspace-scoped shortcuts automatically based on focus:
   - use `PluginHost` focus changes (`on_focus`/`on_defocus`) plus `AppContext.workspace_state`.

### 4) Focus + popout windows

We already have the concept of an active workspace (`workspace_state.active_workspace_id`) and plugin focus hooks.

For shortcuts we need a second axis: **focused window**.

Plan:

- Each top-level window that wants shortcuts constructs its own `ShortcutDispatcher` and attaches it to itself.
- `ShortcutDispatcher` only processes events for its own window.
- Popout windows (created by plugins) are regular `QMainWindow` instances:
  - They create their own dispatcher and register the plugin's workspace-scoped shortcuts there.
  - Result: two plugin windows can run side-by-side and shortcuts naturally route to the one with focus.

### 5) Settings + persistence

Shortcuts are semantic user preferences, so store them in `settings.json` via `SettingsStore` / `DebouncedSettingsWriter`.

Add to `datalens/domain/system/settings.py`:

- `shortcuts: dict[str, dict[str, ShortcutBinding]]`
  - keyed by `plugin_id`, then `command_id`.

Merge behavior:

- Defaults come from plugin registration specs.
- User overrides stored in settings apply on startup and when opening the shortcuts dialog.
- If a plugin is disabled or missing, keep its stored overrides (so re-enabling restores them).

### 6) UI: Keyboard Shortcuts dialog (with plugin pages)

Add a dedicated dialog under `datalens/ui/dialogs/keyboard_shortcuts/`:

- Left side: list of pages (Core, and each enabled plugin page).
- Right side: sections with entries and editable binding widgets.

V1 reference (for parity, not for direct reuse):

- Dialog: `src/datalens/keyboard_shortcuts_dialog.py`
  - `ShortcutTab` -> `ShortcutSection` -> `ShortcutEntry`
  - `QKeySequenceEdit` capture UI for keyboard-only shortcuts
  - Hold/toggle segmented mode widget (see `src/datalens/ui/widgets/toggles.py`)

For V2, we can keep the same conceptual structure (pages/sections/entries) but the editor widget must be custom to support mouse buttons and wheel.

Binding editor requirements:

- "Record..." button that captures the next input chord:
  - keyboard chord: press key with modifiers
  - mouse chord: click button with modifiers
  - wheel chord: scroll with modifiers (capture direction)
- Clear binding (unbind).
- Conflict display:
  - Within the plugin, show a warning and block saving if two commands share the same chord+scope.
  - Across plugins, show an informational warning only (allowed).

### 7) Correctness criteria

- A plugin cannot register duplicate `command_id`s.
- A plugin cannot have two commands bound to the same `InputChord` within the same scope.
- Dispatch never blocks the UI thread.
- Shortcuts only affect the focused window.
- Focus switching for workspaces triggers enable/disable semantics:
  - `on_defocus` runs before switching, then `on_focus` after switching.

### 8) Implementation tasks (ordered)

1) **Domain model**
   - Add `datalens/domain/system/shortcuts.py` with dataclasses + normalization helpers.
2) **AppContext service**
   - Add `ShortcutRegistry` + `ShortcutService` to `AppContext` (`datalens/core/context.py`).
3) **Registration API**
   - Add `ctx.app.shortcuts.register_shortcuts(...)` and plugin-unregister handle.
4) **Dispatcher**
   - Implement `ShortcutDispatcher` (Qt event filter) and per-window attachment.
5) **Persistence**
   - Extend `AppSettings` to store per-plugin overrides and load/apply them on startup.
6) **UI**
   - Implement the shortcuts dialog and integrate under `Help` or `Edit -> Preferences` (decision: keep it in Preferences for V2).
7) **Integration points**
   - MainWindow installs a dispatcher.
   - Plugin popout helper installs a dispatcher automatically.
8) **Validation**
   - Unit tests for parsing/normalization + conflict detection.
   - Manual tests for window focus routing and mouse chord capture.

## Notes / risks (be honest)

- Qt does not provide a unified "shortcut system" that includes mouse+wheel. Keyboard shortcuts (`QShortcut/QAction`) are great, but mouse/wheel require event filtering. That means we must be careful about interfering with normal widget input.
- "Hold vs toggle" semantics get tricky when the trigger includes a mouse button (e.g., `Hold` while pressed). For V1 parity, start with keyboard hold/toggle and mouse press-triggered actions; expand later.
- Popout windows are feasible, but they require plugin authors to register UI and shortcuts per-window. We can provide helpers to make that easy.
