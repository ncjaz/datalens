# Shortcuts system (keyboard + mouse chords)

DataLens V2 provides a first-class shortcuts system that:

- Routes input by **focused top-level window** (MainWindow vs plugin popouts).
- Supports **workspace-scoped** shortcuts (only the active workspace plugin).
- Supports **keyboard**, **mouse button**, and **mouse wheel** chords.
- Stores user overrides in `settings.json` (semantic preference), not QSettings.

## How it works

### Registration

Plugins can optionally implement a `register_shortcuts(ctx)` hook (called right after `on_load`) and register one or more pages.

At runtime, the plugin calls:

- `ctx.app.shortcuts.register_page(plugin_id=..., plugin_name=..., page=..., callbacks=...)`

The registry enforces:

- `command_id` is unique per plugin.
- A plugin cannot bind two commands to the same chord within the same scope.
- `GLOBAL`/`WINDOW` bindings are unique across all plugins (app-level).

## Core app shortcuts (menus)

In V2, the shortcuts system is intended to be the **single source of truth** for core app commands
to avoid QAction/QShortcut "double fire" issues.

The menu bar still uses `QAction`s for presentation, but core keyboard shortcuts are registered via:

- `datalens/src/datalens/ui/shortcuts/core_shortcuts.py`

This means menu actions do **not** need `setShortcut(...)` for these core commands.

### Dispatch

`DatalensApplication` installs an application-wide event filter that converts input events into chord strings and asks the shortcuts service to dispatch.

Dispatch priority is:

1. Workspace scope (active workspace plugin for the focused window)
2. Window scope (focused window + active plugin id)
3. Global scope

Shortcut callbacks must be fast; heavy work must be scheduled onto background systems (loader/threadpool/DB executors).

### Window scope (per-window behavior)

In V2, `WINDOW` scope is routed by the focused window and that window's active plugin id. This allows different plugin
windows to reuse the same `WINDOW` chords without conflicts, while still keeping bindings gated to the focused window.

### Event consumption (don't steal input by default)

When a chord matches and a callback runs, the shortcuts system may optionally **consume** the underlying Qt event (preventing it from reaching the widget).

In V2 we default to *not* consuming events to avoid breaking normal widget interactions.

To consume a matching event, set `consume_event=True` on the `ShortcutCommandSpec`.

### Mouse/wheel chords are opt-in

The application-wide shortcuts event filter runs *before* widgets receive input. Dispatching mouse/wheel chords globally
can interfere with normal widget interactions (dragging, scrolling, painting tools).

So in V2:

- Keyboard chords are dispatched globally for the focused window.
- Mouse/wheel chords are only dispatched globally if the target widget (or its parent chain) opted in by setting
  `datalens.shortcuts.mouse_chords_enabled = True`.

For canvas/tool widgets, the preferred pattern is to dispatch from inside the widget's own event handlers using
`datalens.ui.shortcuts.widget_dispatch.dispatch_shortcut_event(...)`.

If you do want global mouse/wheel chord dispatch for a widget subtree, opt-in by setting
`datalens.shortcuts.mouse_chords_enabled = True` (or call
`datalens.ui.shortcuts.widget_dispatch.enable_mouse_wheel_chords(widget)`).

### Focus + popout windows

- For the MainWindow, workspace focus comes from `WorkspaceStateService.active_workspace_id`.
- For plugin popout windows, you can tag the window with a plugin id:
  - `app_ctx.shortcuts.tag_window_with_plugin(window, plugin_id)`

This allows multiple plugin windows to coexist and still route shortcuts correctly based on which window is focused.

### Persistence (settings.json)

User overrides live under `AppSettings.shortcut_overrides`:

- Keyed by `plugin_id -> command_id -> chord`
- `None` means "unbind"
- Missing entries fall back to the registered default chord
- Hold/Toggle mode overrides (for supported commands) live under `mode_toggle_overrides`

The Preferences page updates settings via `DebouncedSettingsWriter` and applies overrides immediately (no restart needed).

## Hold vs Toggle (keyboard)

Some stateful tools want a **keyboard hold** behavior ("active only while the key is held") but also want a user-configurable
**toggle** behavior ("press once to enable, press again to disable").

In V2:

- The shortcuts system owns the binding and the user's Hold/Toggle preference (Preferences UI).
- The widget/tool owns the press/release lifecycle so we don't globally steal key events.

For these commands, register them with:

- `ShortcutCommandSpec.mode_toggle_default = False|True` (enables the Hold/Toggle control in Preferences)
- `ShortcutCommandSpec.dispatch_globally = False` (handled by the focused widget, not global dispatch)

Widget example:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.hold_toggle import attach_hold_toggle_shortcut


class MyCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        attach_hold_toggle_shortcut(
            self,
            plugin_id=PluginId("annotation"),
            command_id="spotlight_view",
            on_active_changed=self._set_spotlight_active,
            consume_event=True,
        )

    def _set_spotlight_active(self, active: bool) -> None:
        # Apply the view/tool state here (UI thread).
        ...
```

## Holds/gestures (press/drag/release)

For canvas-style tools (drawing/painting), you typically need press/drag/release semantics.
This is intentionally handled at the widget level (so we don't globally intercept mouse input).

Use `GestureRouter` inside your widget and drive it from `mousePressEvent/mouseMoveEvent/mouseReleaseEvent`.

Gesture begin-chords can be declared by plugins in their shortcuts page and edited by users in the same Preferences page.

For a widget to respect user overrides, it should read the effective begin chord from the shortcuts service and build a
`GestureBindingSpec` from that value (see the `widget_test` plugin's gesture panel for an example pattern).

### Canvas example (gesture + discrete chords together)

This example shows the recommended pattern for an annotation canvas:

- Use `GestureRouter` for press/drag/release state (drawing/painting).
- Use `dispatch_shortcut_event(...)` for occasional discrete chords (e.g. `Ctrl+WheelUp` zoom),
  without relying on the global event filter.

```python
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId, GesturePhase
from datalens.ui.shortcuts.gesture_router import GestureRouter
from datalens.ui.shortcuts.widget_dispatch import dispatch_shortcut_event


class AnnotationCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_ctx = get_app_context()
        self._plugin_id = PluginId("annotation")

        begin = self._app_ctx.shortcuts.get_effective_gesture_chord(
            plugin_id=self._plugin_id,
            gesture_id="draw",
            default="Shift+LeftClick",
        )
        spec = GestureBindingSpec(
            gesture_id=GestureId("draw"),
            title="Draw",
            begin_chord=begin,
            consume_event=True,
        )
        self._gesture = GestureRouter(bindings=(spec,), callback=self._on_gesture_phase)

    def _on_gesture_phase(self, spec: GestureBindingSpec, phase: GesturePhase, event) -> bool:
        # BEGIN: start stroke; UPDATE: add points; END: commit stroke; CANCEL: abort.
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._gesture.handle_mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._gesture.handle_mouse_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._gesture.handle_mouse_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        result = dispatch_shortcut_event(shortcuts=self._app_ctx.shortcuts, event=event, widget=self)
        if result.handled and result.consume_event:
            event.accept()
            return
        super().wheelEvent(event)
```

## Files that make up the system

- Domain schema: `datalens/src/datalens/domain/system/shortcuts.py`
- Settings schema: `datalens/src/datalens/domain/system/settings.py`, `datalens/src/datalens/core/app_settings.py`
- Runtime service: `datalens/src/datalens/services/shortcuts/registry.py`, `datalens/src/datalens/services/shortcuts/manager.py`
- Qt input plumbing: `datalens/src/datalens/ui/shortcuts/chords.py`, `datalens/src/datalens/ui/shortcuts/event_filter.py`
- Hold/Toggle helper (widget-local): `datalens/src/datalens/ui/shortcuts/hold_toggle.py`
- Gesture router (widget opt-in): `datalens/src/datalens/ui/shortcuts/gesture_router.py`
- Widget dispatch helper (for mouse chords in canvases/tools): `datalens/src/datalens/ui/shortcuts/widget_dispatch.py`
- Preferences UI: `datalens/src/datalens/ui/menus/edit/preferences/pages/keyboard_shortcuts.py`
- Plugin hook integration: `datalens/src/datalens/services/plugins/runtime/host.py`, `datalens/src/datalens/services/plugins/runtime/contracts.py`

## Plugin example

```python
from datalens.domain.system.shortcuts import (
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from datalens.services.plugins.runtime import PluginAppContext


def register_shortcuts(self, ctx: PluginAppContext) -> None:
    page = ShortcutPageSpec(
        page_id="main",
        title="My Plugin",
        sections=(
            ShortcutSectionSpec(
                section_id="general",
                title="General",
                commands=(
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("toggle_mode"),
                        title="Toggle Mode",
                        default_chord="Ctrl+M",
                        scope=ShortcutScope.WORKSPACE,
                    ),
                ),
            ),
        ),
    )

    ctx.app.shortcuts.register_page(
        plugin_id=self.plugin_id,
        plugin_name=ctx.plugin.name,
        page=page,
        callbacks={
            "toggle_mode": self._toggle_mode,
        },
    )
```

Notes:

- Use `ShortcutScope.WORKSPACE` for commands that should only trigger when your workspace is active.
- If you need to allow chords while typing in a text field, set `allow_in_text_inputs=True`.

## Tooltips (V1-style)

For UI buttons that duplicate a shortcut action, show the effective chord in the tooltip:

- Fetch: `ShortcutsService.get_effective_command_chord(...)`
- Format: `datalens.ui.shortcuts.tooltips.tooltip_with_shortcut(...)`

If you need tooltips to update live after the user edits shortcuts, subscribe to
`ShortcutsService.subscribe_changed(...)` and update the tooltip from that callback.

## Button + Shortcut Helper Utilities

To reduce boilerplate when creating buttons with keyboard shortcuts, use the binding pattern:

### Option 1: All-in-one button creation

Use `ShortcutButtonBinding.create_button()` to create and wire a button in one call:

```python
# In plugin __init__:
self._save_binding = ShortcutButtonBinding(
    command=ShortcutButtonCommand(...),
    callback=self._on_save,
)

# In workspace UI:
btn = self._save_binding.create_button(
    theme=ctx.app.theme,
    parent=parent,
    plugin_id=self.plugin_id,
)
```

### Option 2: Wire existing button to binding

Use `wire_button_to_binding()` from `datalens.ui.shortcuts.helpers` for manual button creation:

```python
from datalens.ui.shortcuts.helpers import wire_button_to_binding

# Create button with custom styling
btn = DatalensButton("Save", ctx.app.theme, ButtonVariant.PRIMARY)
btn.setMinimumWidth(120)

# Wire to binding (connects clicked signal + attaches tooltip)
wire_button_to_binding(btn, binding=plugin.save_binding, plugin_id=plugin.plugin_id)
```

**Key benefit**: Both patterns keep shortcut registration separate from button creation, maintaining
the architectural separation between service layer (shortcuts) and UI layer (widgets).
