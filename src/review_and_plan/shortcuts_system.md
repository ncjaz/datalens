# Input Bindings / Shortcuts System (DataLens V2)

Status: **Implemented (MVP)** for command-style shortcuts; **Implemented (MVP)** for gesture begin-chords + persistence/UI (phases still planned).

This is the single plan/spec for how keyboard + mouse bindings work in V2, and what remains to be built.

Related docs:
- `datalens/src/review_and_plan/overview_architecture.md` (high-level map + status table)
- `docs/events.md` (EventHub API; note: EventHub is for events, not high-rate input)

Key code (MVP):
- Domain schema: `datalens/src/datalens/domain/system/shortcuts.py`
- Settings persistence: `datalens/src/datalens/domain/system/settings.py` (`AppSettings.shortcut_overrides`)
- Services: `datalens/src/datalens/services/shortcuts/registry.py`, `datalens/src/datalens/services/shortcuts/manager.py`
- Qt integration: `datalens/src/datalens/ui/shortcuts/event_filter.py`, `datalens/src/datalens/ui/shortcuts/chords.py`
- Preferences UI: `datalens/src/datalens/ui/menus/edit/preferences/pages/keyboard_shortcuts.py`
- Plugin integration: `datalens/src/datalens/services/plugins/runtime/host.py` (`register_shortcuts` hook)

---

## Executive Summary

We want one unified "Input Bindings" system for developers and users:

- Plugins define commands + default bindings in one place.
- Users can view and override bindings in one Preferences page.
- Dispatch is window-focused and can be workspace/plugin-scoped.
- Dispatch must not block UI and must not break widget input.

Honest framing (this matters):

- Qt is great for discrete keyboard shortcuts (`QAction` / `QShortcut`), but it does not provide a unified, safe, global "mouse shortcuts" system.
- For drawing/painting (press -> move -> release), the correct place is a widget-level state machine (canvas/tool controller), not an app-global shortcut handler.
- To keep it feeling like "one system", we should keep one registry + one settings/UI surface, but accept two delivery paths:
  1) **Command shortcuts** (discrete triggers) - implemented MVP
  2) **Gesture/hold bindings** (begin/update/end/cancel) - planned

---

## Objectives

### Functional
- Support keyboard chords (`Ctrl+M`, `Ctrl+Shift+M`).
- Support mouse + wheel chords (`Ctrl+LeftClick`, `Alt+WheelUp`, etc.).
- Per-window routing: only the focused top-level window receives dispatch.
- Plugin-friendly registration + a shared configuration UI.
- Conflict prevention within a plugin: a plugin must not bind multiple commands to the same chord in the same scope.

### UX / DX
- One Preferences entry point showing:
  - core + per-plugin pages
  - effective binding + conflicts
  - record/clear flows
- Plugins can be enabled/disabled and their overrides persist.

### Constraints (non-negotiable)
- Non-blocking UI: dispatch must be fast; handlers must offload heavy work.
- Do not steal widget input by default (text fields, canvases, custom widgets).
- Keep the system modular (no monoliths).

---

## What's Implemented Today (MVP)

### Supported
- Keyboard + mouse + wheel chords (single-step gestures; not sequences).
- Focused-window routing (focused top-level window only).
- Workspace scoping (workspace/plugin-only bindings when that workspace is active).
- Per-plugin pages in the shortcuts Preferences UI.
- User overrides persisted to `settings.json`.
- Conflict prevention within a plugin/scope.
- Optional `consume_event` per command (defaults off; opt-in when needed).
- Gesture begin-chords surfaced in Preferences and persisted to `settings.json` (used by widget-level `GestureRouter`).

### Not supported yet (planned)
- Full gesture lifecycle integration (BEGIN/UPDATE/END/CANCEL bindings), beyond begin-chord selection.
- Transaction/batching semantics (release-to-commit) for gesture workflows.
- Richer editor UX (search/filter/import/export).

---

## Terminology

- Chord: one input gesture with optional modifiers (e.g. `Ctrl+Shift+M`, `Alt+WheelUp`).
- Command: a named action (e.g. `annotate.delete_selection`).
- Scope: where a binding applies (`global`, `window`, `workspace`).
- Focused window: active top-level Qt window (main window, plugin popout, etc.).
- Focused workspace: active workspace/plugin within the focused window.

---

## MVP Architecture (How It Works)

### Registration (core + plugins)
- A plugin optionally implements `register_shortcuts(...)` (see `SupportsShortcuts`).
- The plugin returns a `ShortcutPageSpec` containing:
  - page label
  - sections
  - commands (ids + titles + default chords)
- The plugin provides callbacks for command ids (registered with the shortcuts manager).

### Persistence and overrides
- Defaults come from page specs at registration time.
- User overrides live in `AppSettings.shortcut_overrides`.
- On startup the registry:
  - loads plugin specs
  - applies stored overrides (best-effort, ignores unknown commands)
- If a plugin is disabled/missing:
  - stored overrides remain in settings so re-enabling restores them.

### Dispatch (focused window + workspace)
- A Qt `eventFilter` receives keyboard/mouse/wheel events.
- The filter normalizes the event to a chord string.
- The manager resolves which binding applies using priority:
  1) focused workspace bindings
  2) window/global bindings
- It executes the registered callback for the resolved command id.

Rule for callback code: keep it fast; schedule heavy work explicitly (loader/threadpool/DB/IO) and marshal results back to UI.

Important robustness rule (developer-facing):
- The application-wide event filter dispatches **keyboard chords** globally, but **mouse/wheel chords are opt-in**.
  - Rationale: the global event filter runs *before* widgets see the event, so mouse/wheel chords can easily interfere
    with normal widget interactions (dragging, scrolling, painting tools).
  - Widgets that want mouse/wheel chords should either:
    - opt-in by setting `datalens.shortcuts.mouse_chords_enabled = True` on the widget (or its parent chain), or
    - dispatch from inside their own event handlers using `datalens.ui.shortcuts.widget_dispatch.dispatch_shortcut_event(...)`.

---

## Key Decisions (Recorded)

### Keep deep code loader-agnostic
Shortcut callbacks should not require special parameters (like a loader context). If a callback needs UX, it explicitly starts a loader (or publishes progress logs if a loader is active).

### Prevent conflicts where it matters
We block conflicts within a plugin to avoid "one plugin binds two actions to the same chord". Cross-plugin conflicts are currently allowed because routing is workspace-focused; UX will be improved later.

For `GLOBAL`/`WINDOW` scope, conflicts are blocked across *all* plugins: those bindings are app-level and must be unique in the focused window.

### Core app commands are registered in the shortcuts system
To avoid QAction/QShortcut double-fire, core menu commands are registered as a "Core" shortcuts page and QAction shortcuts are not used as the source of truth.

### One system UX, two delivery paths
Command shortcuts are global/window/workspace scoped and handled centrally. Gesture/hold bindings are widget-level and stateful (begin/update/end), but will share the same registry/settings/UI surface so the system still feels unified.

---

## Key Considerations (Before We Add Holds/Gestures)

### Do not break widgets
If we globally intercept mouse events we will ruin:
- text selection and editing
- drag interactions (splitters, sliders, list drag)
- canvas tools (drawing/painting)

So the default must be observe-and-dispatch for discrete commands, not capture-and-swallow input.

### Holds/gestures are not commands
Holds (Shift held while clicking multiple times, then release merges work) require:
- begin (press)
- update (move/drag / repeated clicks)
- end (release)
- cancel (focus lost / escape / context change)

This belongs with the widget/tool controller because it needs local state, high-rate move events, and explicit ownership of the interaction.

### Focus and popouts
Routing must consider:
- focused top-level window
- focused workspace within that window

When we support popout windows, only one window is focused at a time, so dispatch should naturally route correctly as long as we key off Qt window focus.

---

## Planned Work (Next Iteration)

### A) Command "consume event" control (implemented)
- `consume_event` exists on `ShortcutCommandSpec` (default off).
- Preferences UI exposes a per-binding "Consume" toggle.
- Event filter consumes only when the binding says to consume.

### B) Gesture/hold bindings (unified with the same registry/UI)
Goal: support press/hold/release workflows (drawing/painting style interactions) without global event stealing.

Design:
- Keep global manager for commands.
- Add a widget-level `GestureRouter` that:
  - receives raw mouse/key events via the widget's normal event handlers
  - resolves them through the shared registry (gesture bindings)
  - runs a state machine: `begin -> update -> end/cancel`

Tasks:
- Domain:
  - Add `GestureBindingSpec` (id, title, begin chord, scope, consume) (implemented for begin-chords).
  - Add `GesturePhase` enum (`BEGIN`, `UPDATE`, `END`, `CANCEL`).
- Services:
  - Extend the registry to store gesture bindings alongside command bindings (implemented).
  - Extend overrides persistence to cover gesture bindings (implemented).
- UI:
  - Display gesture bindings in the same Preferences page (implemented for begin-chords).
  - Recording UX supports begin-chords (keypress/mouse press/wheel) (implemented).
- Widget integration:
  - Provide a small helper/mixin for canvas-like widgets to call into the router.
  - Provide `GestureRouter` (implemented) and a reference panel in `widget_test` (implemented).

### C) Focus-driven activation (window/workspace) for both paths
Goal: a binding only applies when its window/workspace is actually focused.

Tasks:
- Ensure the shortcuts manager's focus context is updated on:
  - workspace switch (focus/defocus)
  - window activation
- For gestures: router consults the same "active workspace id" context.

### D) Transaction/merge semantics (release-to-commit)
Goal: workflows like "hold Shift, do multiple operations, release merges into one".

Tasks:
- Define an optional transaction key / batch policy in gesture specs.
- Provide a lightweight helper in the annotation domain/service layer to batch operations and commit on `END`.

### E) Documentation + validation
Tasks:
- Add/expand a Sphinx concept page for "Input Bindings" that explains:
  - command shortcuts vs gestures
  - focus routing rules
  - plugin registration patterns
- Add automated tests:
  - chord parsing/normalization
  - conflict detection
  - consume_event behavior (unit-level)
- Add widget_test plugin demos:
  - command shortcut demo (already exists)
  - hold/drag gesture demo (planned)

---

## Correctness Criteria (Definition of Done for the next iteration)

- No measurable UI lag introduced by bindings dispatch.
- Command dispatch does not prevent normal widget interaction by default.
- Gesture bindings can implement a real press/drag/release interaction without global event filters.
- Bindings are routed to the focused window and (when applicable) the focused workspace.
- Preferences UI can list and edit both commands and gesture bindings without confusion.
