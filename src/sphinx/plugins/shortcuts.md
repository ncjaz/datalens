# Shortcuts and Gestures (Plugin Developer Guide)

This page explains how plugins should use the V2 shortcuts system without breaking normal widget input.

## Two input paths (one unified configuration UI)

DataLens V2 intentionally uses two paths:

- **Command shortcuts** (discrete triggers): keyboard chords and optional mouse/wheel chords that call a callback.
- **Gestures/holds** (stateful tools): press/drag/release workflows implemented in the widget/tool controller.

Both can be declared by a plugin in the same shortcuts page (so users configure them in one place).

## Registering command shortcuts

Implement `register_shortcuts(ctx)` in your plugin runtime and register a `ShortcutPageSpec`.

Use `ShortcutScope.WORKSPACE` for workspace-only commands (recommended for most plugin actions).

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
        callbacks={"toggle_mode": self._toggle_mode},
    )
```

### Avoid firing while the user is typing

By default, commands do **not** fire when a text input has focus.

If a command must work while typing (rare), set:

- `allow_in_text_inputs=True`

### Consuming events

`consume_event` controls whether the Qt event should stop at the shortcut handler.

- Default is `False` (recommended).
- Use `True` only when you are sure the underlying widget should not receive the event.

## Registering gestures (begin-chords)

Gestures are stateful tools (press/drag/release). The shortcuts system currently persists and exposes **begin chords**
for gestures, while the widget implements the lifecycle.

Declare a `GestureBindingSpec` alongside your commands:

```python
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId

GestureBindingSpec(
    gesture_id=GestureId("draw"),
    title="Draw",
    begin_chord="Shift+LeftClick",
)
```

## Using GestureRouter in a canvas/tool widget

Recommended pattern:

- Use `GestureRouter` to own press/drag/release state.
- Pull the effective begin chord from the shortcuts service (so user overrides apply).

```python
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId, GesturePhase
from datalens.ui.shortcuts.gesture_router import GestureRouter


class Canvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        app_ctx = get_app_context()
        plugin_id = PluginId("annotation")

        begin = app_ctx.shortcuts.get_effective_gesture_chord(
            plugin_id=plugin_id,
            gesture_id="draw",
            default="Shift+LeftClick",
        )

        spec = GestureBindingSpec(gesture_id=GestureId("draw"), title="Draw", begin_chord=begin)
        self._router = GestureRouter(bindings=(spec,), callback=self._on_phase)

    def _on_phase(self, spec: GestureBindingSpec, phase: GesturePhase, event) -> bool:
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._router.handle_mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)
```

## Discrete mouse/wheel chords inside a widget

If you want mouse/wheel chords for a widget (e.g. `Ctrl+WheelUp` zoom), do *not* rely on the global event filter.
Dispatch from inside the widget:

```python
from datalens.ui.shortcuts.widget_dispatch import dispatch_shortcut_event
```

This keeps canvas input smooth and avoids global interception.

## Modifier-click UI buttons (widget-local)

Sometimes you want a small UI affordance where a *normal click* does one action, but a *modifier click* does another
(e.g. `Click` refresh once, `Shift+Click` toggle auto-refresh).

Use the widget-local helper (does not register a global shortcut and does not interfere with canvas input):

- `datalens.ui.widgets.core.modifier_click.ModifierClickRouter`

Example:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from datalens.ui.widgets.core.modifier_click import ModifierClickAction, ModifierClickRouter

btn = QToolButton()

ModifierClickRouter(
    btn,
    actions=(
        ModifierClickAction(required_modifiers=Qt.ShiftModifier, callback=toggle_auto_refresh),
        # Fallback: any modifiers -> refresh once (consume to avoid accidental toggles)
        ModifierClickAction(required_modifiers=Qt.NoModifier, callback=refresh_once, exact_match=False),
    ),
)
```

Notes:

- Keep this behavior *per-widget*, not global, to avoid unexpected interception.
- If you want a fully user-rebindable modifier/mouse chord, use the shortcuts/gesture system instead.

### Widget integration helper

For common UI wiring (opt-in mouse/wheel chords, popout window tagging, and live refresh),
use:

- `datalens.ui.shortcuts.helpers.attach_shortcut_integration(...)`

Example:

```python
from datalens.ui.shortcuts.helpers import attach_shortcut_integration

# For a canvas widget that wants global mouse/wheel chords:
attach_shortcut_integration(canvas_widget, enable_mouse_wheel=True)

# For a plugin popout window (workspace-scoped routing):
attach_shortcut_integration(popout_root, plugin_id=self.plugin_id, tag_window=True)
```

## Adding shortcuts to tooltips (V1-style)

If your plugin provides both a UI button and a shortcut for the same action, it is useful to show the *current effective*
shortcut (after user overrides) in the tooltip.

Use:

- `ShortcutsService.get_effective_command_chord(...)` to fetch the effective chord.
- `datalens.ui.shortcuts.tooltips.tooltip_with_shortcut(...)` to format a tooltip consistently.

Example:

```python
from datalens.ui.shortcuts.tooltips import tooltip_with_shortcut

chord = ctx.app.shortcuts.get_effective_command_chord(
    plugin_id=self.plugin_id,
    command_id="toggle_mode",
)
button.setToolTip(
    tooltip_with_shortcut(
        title="Toggle Mode",
        description="Toggles the main mode for this tool.",
        shortcut=chord,
    )
)
```

Notes:

- This is a UI convenience only. It does not change shortcut dispatch.
- Tooltips are usually set once when the widget is created. If you need to reflect shortcut changes live, rebuild tooltips
  when your preferences UI closes, or subscribe to `ShortcutsService.subscribe_changed(...)` and update the tooltip from
  that callback.

### Reducing duplication: one definition for button + shortcut

If you often have a UI button and a shortcut that should run the same callback, prefer declaring the command once and
reusing it for both UI and shortcut registration.

DataLens provides lightweight helpers (see {doc}`ui_commands` for the full guide):

- `ShortcutButtonCommand` / `ShortcutButtonBinding` (Qt-light declarations)
- `register_shortcut_page_for_buttons(...)` (registers a page + callbacks)
- `ShortcutButtonBinding.create_button(...)` (creates a wired button with one call)
- `wire_button_to_binding(...)` (wires an existing button to a binding)
- `DatalensButton.attach_shortcut_tooltip(...)` (keeps tooltips synced to overrides)

#### Pattern 1: `create_button()` (all-in-one)

```python
from datalens.api.plugins import (
    PluginAppContext,
    ShortcutButtonBinding,
    ShortcutButtonCommand,
    ShortcutCommandId,
    register_shortcut_page_for_buttons,
)


class MyPlugin:
    def __init__(self) -> None:
        self._next_image = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("next_image"),
                title="Next image",
                description="Advance to the next image in the current dataset.",
                default_chord="Right",
            ),
            callback=self._go_next_image,
        )

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        register_shortcut_page_for_buttons(
            ctx,
            page_id="main",
            page_title="My Plugin",
            section_id="navigation",
            section_title="Navigation",
            bindings=(self._next_image,),
        )

    def create_workspace_widget(self, parent, ctx: PluginAppContext):
        # One-liner: creates button + wires callback + attaches tooltip
        button = self._next_image.create_button(
            theme=ctx.app.theme,
            parent=parent,
            plugin_id=self.plugin_id,
        )
        return button
```

#### Pattern 2: `wire_button_to_binding()` (manual button creation)

If you need more control over button styling or want to create the button separately:

```python
from datalens.ui.widgets.core.buttons import DatalensButton, ButtonVariant
from datalens.ui.shortcuts.helpers import wire_button_to_binding


class MyWorkspace(QWidget):
    def __init__(self, ctx: PluginProjectContext, plugin: MyPlugin):
        # Create button with custom styling
        self._next_btn = DatalensButton(
            "Next",
            ctx.app.theme,
            ButtonVariant.PRIMARY,
        )
        self._next_btn.setMinimumWidth(120)

        # Wire to already-registered binding (2nd line)
        wire_button_to_binding(
            self._next_btn,
            binding=plugin.next_image_binding,
            plugin_id=plugin.plugin_id,
        )
```

**Benefits of both patterns:**
- Shortcut registration happens **once** in `register_shortcuts()` (separate from UI)
- Button creation happens on-demand in the UI layer
- Shortcuts work even if button isn't rendered yet
- User can configure shortcuts before opening the workspace
- No duplication of command metadata
- Tooltips auto-update when user changes shortcuts

This intentionally does **not** set Qt-level shortcuts (`QAction.setShortcut`, `QShortcut`), so the managed shortcuts
system remains the single source of truth and the callback doesn't double-fire.
