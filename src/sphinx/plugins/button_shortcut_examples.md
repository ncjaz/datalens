# Button + Shortcut Integration Examples

This page provides practical examples for integrating buttons with keyboard shortcuts in plugins.

## Why use this pattern?

**Problem**: You want both a UI button and a keyboard shortcut to trigger the same action.

**Anti-pattern** ❌: Registering shortcuts during button creation
- Shortcuts won't exist until button is rendered
- Breaks lazy loading and conditional UI
- User can't configure shortcuts until workspace is opened

**Correct pattern** ✅: Register shortcuts in `register_shortcuts()`, create buttons separately
- Shortcuts exist from app startup
- UI can create/destroy buttons freely
- User can configure shortcuts in Preferences at any time

## Pattern 1: All-in-one with `create_button()`

**Best for**: Simple cases where you don't need custom button styling.

### Plugin service layer

```python
from datalens.api.plugins import (
    BasePlugin,
    PluginAppContext,
    PluginProjectContext,
    ShortcutButtonBinding,
    ShortcutButtonCommand,
    ShortcutCommandId,
    ShortcutScope,
    register_shortcut_page_for_buttons,
)


class MyPlugin(BasePlugin):
    def __init__(self) -> None:
        # Define binding once (reused for shortcuts + UI)
        self._save_image = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("save_image"),
                title="Save Image",
                button_text="Save",
                description="Save the current frame to the project directory.",
                default_chord="Ctrl+S",
                scope=ShortcutScope.WORKSPACE,
            ),
            callback=self._on_save_image,
        )

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        # Register shortcuts page (happens during on_load, before UI exists)
        register_shortcut_page_for_buttons(
            ctx,
            page_id="main",
            page_title="My Plugin",
            section_id="actions",
            section_title="Actions",
            bindings=[self._save_image],
        )

    def _on_save_image(self) -> None:
        # Implementation here
        pass
```

### UI layer (workspace widget)

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
from datalens.api.plugins import PluginProjectContext
from datalens.ui.widgets.core.buttons import ButtonVariant


class MyWorkspace(QWidget):
    def __init__(self, ctx: PluginProjectContext, plugin: MyPlugin):
        super().__init__()

        # One-liner: creates button + wires callback + attaches tooltip
        save_btn = plugin._save_image.create_button(
            theme=ctx.app.theme,
            parent=self,
            plugin_id=plugin.plugin_id,
            variant=ButtonVariant.PRIMARY,
        )

        layout = QVBoxLayout(self)
        layout.addWidget(save_btn)
```

**Result**:
- Shortcut registered ✅
- Button created and wired ✅
- Tooltip shows "Save Image (Ctrl+S)" ✅
- User can rebind shortcut in Preferences ✅

---

## Pattern 2: Manual styling with `wire_button_to_binding()`

**Best for**: Cases where you need custom button styling, sizing, or conditional rendering.

### Plugin service layer

```python
# Same as Pattern 1 - identical service layer code
class MyPlugin(BasePlugin):
    def __init__(self) -> None:
        self._refresh = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("refresh_devices"),
                title="Refresh Devices",
                button_text="Refresh",
                description="Re-enumerate connected camera devices.",
                default_chord="F5",
                scope=ShortcutScope.WORKSPACE,
            ),
            callback=self._on_refresh,
        )

    # ... register_shortcuts() same as above
```

### UI layer (workspace widget)

```python
from PySide6.QtWidgets import QWidget, QHBoxLayout
from datalens.ui.widgets.core.buttons import DatalensButton, ButtonVariant
from datalens.ui.shortcuts import wire_button_to_binding


class MyWorkspace(QWidget):
    def __init__(self, ctx: PluginProjectContext, plugin: MyPlugin):
        super().__init__()

        # Create button with custom styling
        self._refresh_btn = DatalensButton(
            "Refresh",
            ctx.app.theme,
            ButtonVariant.SECONDARY,
            self,
            outlined=True,
        )
        self._refresh_btn.setMinimumWidth(100)
        self._refresh_btn.setMaximumHeight(28)

        # Wire to binding (2nd step - connects signal + tooltip)
        wire_button_to_binding(
            self._refresh_btn,
            binding=plugin._refresh,
            plugin_id=plugin.plugin_id,
        )

        layout = QHBoxLayout(self)
        layout.addWidget(self._refresh_btn)
```

**Result**:
- Same registration benefits as Pattern 1
- Full control over button appearance
- Still maintains separation of concerns

---

## Pattern 3: Multiple buttons in one section

```python
class MyPlugin(BasePlugin):
    def __init__(self) -> None:
        # Multiple related actions
        self._next = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("next_image"),
                title="Next Image",
                button_text="Next",
                default_chord="Right",
            ),
            callback=self._go_next,
        )

        self._prev = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("prev_image"),
                title="Previous Image",
                button_text="Previous",
                default_chord="Left",
            ),
            callback=self._go_prev,
        )

        self._first = ShortcutButtonBinding(
            command=ShortcutButtonCommand(
                command_id=ShortcutCommandId("first_image"),
                title="First Image",
                button_text="First",
                default_chord="Home",
            ),
            callback=self._go_first,
        )

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        # All three actions in one section
        register_shortcut_page_for_buttons(
            ctx,
            page_id="main",
            page_title="My Plugin",
            section_id="navigation",
            section_title="Navigation",
            section_description="Navigate through the dataset",
            bindings=[self._prev, self._next, self._first],
        )
```

In UI:
```python
# All three buttons created and wired
prev_btn = plugin._prev.create_button(theme=ctx.app.theme, parent=self, plugin_id=plugin.plugin_id)
next_btn = plugin._next.create_button(theme=ctx.app.theme, parent=self, plugin_id=plugin.plugin_id)
first_btn = plugin._first.create_button(theme=ctx.app.theme, parent=self, plugin_id=plugin.plugin_id)
```

---

## Pattern 4: Conditional button rendering

Shortcuts registered **regardless** of whether button is shown:

```python
class MyWorkspace(QWidget):
    def __init__(self, ctx: PluginProjectContext, plugin: MyPlugin):
        super().__init__()

        # Shortcut ALWAYS works (registered in register_shortcuts)
        # Button only shown when project is open
        if ctx.project.root is not None:
            save_btn = plugin._save.create_button(
                theme=ctx.app.theme,
                parent=self,
                plugin_id=plugin.plugin_id,
            )
            layout.addWidget(save_btn)

        # Keyboard shortcut (Ctrl+S) works even when button isn't visible!
```

---

## Common mistakes

### ❌ Mistake 1: Mixing registration and UI creation

```python
# DON'T DO THIS
def create_workspace_widget(self, parent, ctx):
    btn = DatalensButton(...)
    # ❌ Registering during UI creation - TOO LATE
    ctx.app.shortcuts.register_page(...)
    return btn
```

### ❌ Mistake 2: Duplicating command metadata

```python
# DON'T DO THIS
self._save = ShortcutButtonBinding(
    command=ShortcutButtonCommand(command_id="save", title="Save", ...),
    callback=self._save,
)

# Later in UI...
btn = DatalensButton("Save", ...)  # ❌ Duplicating "Save" text
btn.clicked.connect(self._save)     # ❌ Duplicating callback wiring
btn.setToolTip("Save (Ctrl+S)")     # ❌ Duplicating shortcut display
```

**Fix**: Use `create_button()` or `wire_button_to_binding()` to avoid duplication.

### ❌ Mistake 3: Not storing bindings on plugin instance

```python
# DON'T DO THIS
def register_shortcuts(self, ctx):
    # ❌ Binding is local - can't reuse in UI layer
    save = ShortcutButtonBinding(...)
    register_shortcut_page_for_buttons(ctx, bindings=[save])
```

**Fix**: Store bindings as instance attributes in `__init__()`.

---

## Summary

| Pattern | Use When | Lines of Code (UI) |
|---------|----------|-------------------|
| `create_button()` | Default choice, simple styling | 1 line |
| `wire_button_to_binding()` | Need custom styling | 2 lines (create + wire) |
| Manual wiring | Need very fine-grained control | 3-4 lines |

**Always**:
- Define bindings in plugin `__init__()`
- Register in `register_shortcuts()`
- Create UI in `create_workspace_widget()`

**Never**:
- Register shortcuts during UI creation
- Duplicate command metadata between layers
- Use `QAction.setShortcut()` or `QShortcut` (conflicts with managed shortcuts)
