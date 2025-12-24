# UI Command Bindings (Buttons, Menus, Toggles)

DataLens V2 uses a managed shortcuts system (`ShortcutsService`) as the single source of truth for:

- which commands exist
- their default chords
- user overrides (Preferences -> Keyboard Shortcuts)
- scope routing (global/window/workspace)
- conflict detection

At the same time, UI widgets (buttons/checkboxes/toggles/menus) are created and destroyed as the UI is rebuilt.

This page documents a small set of **UI command binding helpers** that reduce duplication between:

- shortcut command registration (plugin runtime, app/service layer)
- UI trigger widgets (Qt UI layer)

The helpers live in:

- `datalens.api.ui_commands`

## Why this is split (and not “register shortcuts from the widget”)

It is tempting to put shortcut registration next to widget creation (e.g. `button.register_shortcut(...)`), but that causes
problems in practice:

- **Preferences needs commands even when UI isn't open**: users should be able to view/edit shortcuts without first opening
  a specific workspace tab.
- **Widget lifecycles are noisy**: widgets are rebuilt; if widgets register commands, you risk duplicate registrations,
  missing registrations, or ordering bugs.
- **Threading and layering**: plugin `register_shortcuts(...)` is designed to be lightweight and Qt-safe; widget creation must
  happen on the Qt UI thread.

So the rule is:

- **Register commands in `register_shortcuts(ctx)`**
- **Create widgets in UI code**
- **Never set `QAction.setShortcut(...)` or create `QShortcut` for these commands**

Instead, use the managed shortcuts system for keyboard chords, and use UI bindings to keep your button/menu/tooltip in sync.

## Momentary commands (buttons + menu actions)

Momentary commands are discrete actions (e.g. "Next image", "Open project", "Run loader").

### Define the command once (plugin)

```python
from datalens.api.plugins import (
    ShortcutButtonBinding,
    ShortcutButtonCommand,
    ShortcutCommandId,
    ShortcutScope,
)


class MyPlugin:
    def __init__(self) -> None:
        self._next_image = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("next_image"),
                title="Next image",
                button_text="Next",
                description="Advance to the next image.",
                default_chord="Right",
                scope=ShortcutScope.WORKSPACE,
                consume_event=True,
            ),
            callback=self._go_next_image,
        )
```

### Register it for Preferences + dispatch (plugin)

You still register a `ShortcutCommandSpec` (the underlying contract), but it is derived from your command definition:

```python
from datalens.api.plugins import PluginAppContext, ShortcutPageSpec, ShortcutSectionSpec


def register_shortcuts(self, ctx: PluginAppContext) -> None:
    page = ShortcutPageSpec(
        page_id="main",
        title="My Plugin",
        sections=(
            ShortcutSectionSpec(
                section_id="navigation",
                title="Navigation",
                commands=(self._next_image.command.to_shortcut_spec(),),
            ),
        ),
    )
    ctx.app.shortcuts.register_page(
        plugin_id=self.plugin_id,
        plugin_name=ctx.plugin.name,
        page=page,
        callbacks={str(self._next_image.command.command_id): self._next_image.callback},
    )
```

### Create a button (UI)

```python
from datalens.domain.plugin import PluginId
from datalens.ui.widgets.core.buttons import ButtonVariant


btn = self._next_image.create_button(
    theme=ctx.app.theme,
    parent=some_widget,
    plugin_id=PluginId("my_plugin"),
    variant=ButtonVariant.PRIMARY,
)
```

What this does:

- creates a `DatalensButton` with the chosen label
- wires `clicked` to the same callback used by the shortcut
- keeps the tooltip showing the *effective* shortcut chord (including user overrides)

### Create a menu/toolbar action (UI)

```python
action = self._next_image.create_action(
    parent=some_menu_or_window,
    plugin_id=PluginId("my_plugin"),
)
some_menu.addAction(action)
```

Notes:

- The action is wired to the same callback.
- It intentionally does **not** call `action.setShortcut(...)`.

## Boolean toggles (checkbox + shortcut)

For a checkbox-like state, you usually want:

- a checkbox that sets the state explicitly (`True/False`)
- a shortcut that toggles that state (`not current`)

Use `ShortcutCheckBoxBinding` when you have a shared state store (service/model/controller) that both UI and shortcut
callbacks can call into.

```python
from collections.abc import Callable

from datalens.api.plugins import (
    ShortcutCheckBoxBinding,
    ShortcutCheckBoxCommand,
    ShortcutCommandId,
)


class MyPlugin:
    def __init__(self) -> None:
        self._enabled = False
        self._enabled_changed: list[Callable[[], None]] = []

        self._enabled_binding = ShortcutCheckBoxBinding(
            command=ShortcutCheckBoxCommand(
                command_id=ShortcutCommandId("toggle_enabled"),
                title="Toggle enabled",
                checkbox_text="Enabled",
                default_chord="Ctrl+E",
            ),
            get_checked=self._get_enabled,
            set_checked=self._set_enabled,
            subscribe_changed=self._subscribe_enabled_changed,  # optional but recommended
        )

    def _get_enabled(self) -> bool:
        return bool(self._enabled)

    def _set_enabled(self, value: bool) -> None:
        value = bool(value)
        if self._enabled == value:
            return
        self._enabled = value
        for cb in tuple(self._enabled_changed):
            cb()
```

Registration uses the derived spec and the binding’s `toggle()` as the shortcut callback:

```python
commands=(self._enabled_binding.command.to_shortcut_spec(),)
callbacks={str(self._enabled_binding.command.command_id): self._enabled_binding.toggle}
```

UI code builds the checkbox from the binding:

```python
cb = self._enabled_binding.create_checkbox(
    theme=ctx.app.theme,
    parent=some_widget,
    plugin_id=PluginId("my_plugin"),
)
```

## Two-state selection (segmented 2-button toggle + shortcut)

For a two-state mode selector (e.g. Global/Project), use `ShortcutTwoStateToggleBinding`:

```python
from datalens.api.plugins import (
    ShortcutTwoStateToggleBinding,
    ShortcutTwoStateToggleCommand,
    TwoStateOption,
    ShortcutCommandId,
)


self._scope_binding = ShortcutTwoStateToggleBinding(
    command=ShortcutTwoStateToggleCommand(
        command_id=ShortcutCommandId("flip_scope"),
        title="Flip scope",
        left=TwoStateOption(id="global", label="Global"),
        right=TwoStateOption(id="project", label="Project"),
        default_chord="Ctrl+G",
    ),
    get_current_id=self._get_scope_mode,
    set_current_id=self._set_scope_mode,
    subscribe_changed=self._subscribe_scope_changed,  # optional but recommended
)
```

Register it with:

```python
commands=(self._scope_binding.command.to_shortcut_spec(),)
callbacks={str(self._scope_binding.command.command_id): self._scope_binding.toggle}
```

And build the UI control:

```python
toggle = self._scope_binding.create_toggle(
    theme=ctx.app.theme,
    parent=some_widget,
    plugin_id=PluginId("my_plugin"),
)
```

## How the pieces “know about each other”

There is no global magic wiring between a button and a shortcut.

Both input paths converge because they ultimately invoke the **same callback/state mutation**:

- Shortcut path:
  - Qt key event -> chord string
  - `ShortcutsService.dispatch(...)` invokes the registered callback for that command id
- UI path:
  - Button/menu/checkbox/toggle emits a Qt signal
  - The binding connects that signal to the same callback (momentary) or the same state setter (toggle)

Bindings exist to keep the command metadata (title/description/default chord) and the UI label/tooltip consistent while
still respecting the correct lifecycle boundaries (register in `register_shortcuts`, create widgets on the UI thread).
