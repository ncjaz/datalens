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
