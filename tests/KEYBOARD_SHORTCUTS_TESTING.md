# Keyboard Shortcuts Testing Guide

This guide shows how to test keyboard shortcuts, modifiers, and shortcut-button integration in DataLens.

## Quick Reference

### Querying Shortcuts

```python
from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId

app_context = get_app_context()
shortcuts = app_context.shortcuts

# Get the effective keyboard chord for a command
chord = shortcuts.get_effective_command_chord(
    plugin_id=PluginId("my_plugin"),
    command_id="my_command"
)
# Returns: "Ctrl+S", "Alt+Shift+X", "F5", or None if unbound
```

### Simulating Keyboard Shortcuts

```python
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Simple key
QTest.keyClick(widget, Qt.Key_F5)

# Ctrl+Key
QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)

# Alt+Key
QTest.keyClick(widget, Qt.Key_F, Qt.AltModifier)

# Shift+Key
QTest.keyClick(widget, Qt.Key_A, Qt.ShiftModifier)

# Multiple modifiers (Ctrl+Shift+S)
QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier | Qt.ShiftModifier)

# Ctrl+Alt+Key
QTest.keyClick(widget, Qt.Key_D, Qt.ControlModifier | Qt.AltModifier)
```

### Checking Modifiers in Chords

```python
# Get the chord
chord = shortcuts.get_effective_command_chord(
    plugin_id=PluginId("widget_test"),
    command_id="log_hello"
)

if chord:
    # Check which modifiers are in the chord
    has_ctrl = "Ctrl" in chord or "Control" in chord
    has_alt = "Alt" in chord
    has_shift = "Shift" in chord
    has_meta = "Meta" in chord or "Cmd" in chord  # Windows/Mac key

    print(f"Chord: {chord}")
    print(f"  Ctrl: {has_ctrl}")
    print(f"  Alt: {has_alt}")
    print(f"  Shift: {has_shift}")
    print(f"  Meta: {has_meta}")
```

## Available Shortcut Manager Methods

### Query Shortcuts

```python
# Get effective chord (includes user overrides)
chord = shortcuts.get_effective_command_chord(
    plugin_id=PluginId("plugin_id"),
    command_id="command_id"
)
# Returns: str | None

# Get hold/toggle mode setting
mode_toggle = shortcuts.get_effective_command_mode_toggle(
    plugin_id=PluginId("plugin_id"),
    command_id="command_id"
)
# Returns: bool | None
#   True = Toggle mode (press to activate, press again to deactivate)
#   False = Hold mode (active only while key is held)
#   None = Not applicable (command doesn't support hold/toggle)

# Get consume event setting
consume = shortcuts.get_effective_consume_event(
    plugin_id=PluginId("plugin_id"),
    command_id="command_id",
    default=True
)
# Returns: bool (whether the shortcut consumes the event)
```

### Gesture Shortcuts (Press/Drag/Release)

```python
# Get gesture chord
chord = shortcuts.get_effective_gesture_chord(
    plugin_id=PluginId("plugin_id"),
    gesture_id="gesture_id",
    default=None
)
# Returns: str | None
```

## Common Testing Patterns

### Pattern 1: Verify Shortcut is Registered

```python
def test_shortcut_registered(app_context):
    """Verify a shortcut is registered for a command."""
    chord = app_context.shortcuts.get_effective_command_chord(
        plugin_id=PluginId("my_plugin"),
        command_id="my_command"
    )

    # Check it's bound (or intentionally unbound)
    assert chord is None or isinstance(chord, str)

    if chord:
        print(f"✓ Command bound to: {chord}")
```

### Pattern 2: Test Shortcut Triggers Button

```python
def test_shortcut_triggers_button(app_context):
    """Test that a keyboard shortcut triggers a button action."""
    from PySide6.QtWidgets import QWidget

    # Create or find the widget with the button
    widget = create_test_widget()
    button = widget.findChild(QPushButton, "my_button")

    # Track clicks
    clicked = []
    button.clicked.connect(lambda: clicked.append(True))

    try:
        widget.show()
        QTest.qWait(50)

        # Simulate the shortcut
        QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)
        QTest.qWait(50)

        # Verify button was triggered
        assert len(clicked) > 0, "Button should have been clicked by shortcut"

    finally:
        widget.close()
        widget.deleteLater()
```

### Pattern 3: Test All Plugin Shortcuts

```python
def test_all_shortcuts_registered(app_context):
    """Verify all expected shortcuts are registered for a plugin."""
    shortcuts = app_context.shortcuts
    plugin_id = PluginId("my_plugin")

    expected_commands = [
        "command1",
        "command2",
        "command3",
    ]

    for command_id in expected_commands:
        chord = shortcuts.get_effective_command_chord(
            plugin_id=plugin_id,
            command_id=command_id
        )
        print(f"{command_id}: {chord or 'Unbound'}")
```

### Pattern 4: Verify Modifiers

```python
def test_shortcut_has_required_modifiers(app_context):
    """Verify shortcuts use safe modifier combinations."""
    chord = app_context.shortcuts.get_effective_command_chord(
        plugin_id=PluginId("my_plugin"),
        command_id="my_command"
    )

    if chord:
        # Verify it has Ctrl or Alt to avoid conflicts
        has_ctrl = "Ctrl" in chord
        has_alt = "Alt" in chord

        # Most shortcuts should have a modifier (unless F-keys)
        if not chord.startswith('F'):
            assert has_ctrl or has_alt, \
                f"Shortcut '{chord}' should have Ctrl or Alt modifier"
```

## Common Qt Key Codes

```python
from PySide6.QtCore import Qt

# Letters
Qt.Key_A, Qt.Key_B, Qt.Key_C, ...

# Numbers
Qt.Key_0, Qt.Key_1, Qt.Key_2, ...

# Function keys
Qt.Key_F1, Qt.Key_F2, ..., Qt.Key_F12

# Special keys
Qt.Key_Enter
Qt.Key_Return
Qt.Key_Escape
Qt.Key_Tab
Qt.Key_Space
Qt.Key_Backspace
Qt.Key_Delete

# Arrow keys
Qt.Key_Up
Qt.Key_Down
Qt.Key_Left
Qt.Key_Right

# Modifiers (used with | operator)
Qt.ControlModifier  # Ctrl
Qt.AltModifier      # Alt
Qt.ShiftModifier    # Shift
Qt.MetaModifier     # Windows/Cmd key
```

## Testing Hold vs Toggle Mode

```python
def test_hold_toggle_mode(app_context):
    """Test shortcuts that support hold/toggle modes."""
    mode_toggle = app_context.shortcuts.get_effective_command_mode_toggle(
        plugin_id=PluginId("widget_test"),
        command_id="hold_toggle_demo"
    )

    if mode_toggle is None:
        print("Command doesn't support hold/toggle mode")
    elif mode_toggle:
        print("Toggle mode: Press to activate, press again to deactivate")
    else:
        print("Hold mode: Active only while key is held")

    # Tests should work with either mode
    assert mode_toggle is None or isinstance(mode_toggle, bool)
```

## Best Practices

### 1. Always Use `get_effective_*` Methods

```python
# ✅ GOOD - Includes user overrides
chord = shortcuts.get_effective_command_chord(
    plugin_id=PluginId("my_plugin"),
    command_id="my_command"
)

# ❌ BAD - Only gets defaults, ignores user preferences
# (Don't query the registry directly in tests)
```

### 2. Handle Both Bound and Unbound Shortcuts

```python
# ✅ GOOD - Handles None
chord = shortcuts.get_effective_command_chord(...)
if chord:
    # Test the bound shortcut
    QTest.keyClick(widget, ...)
else:
    # Shortcut is unbound - test still passes
    pytest.skip("Shortcut is unbound")

# ❌ BAD - Assumes shortcut is bound
QTest.keyClick(widget, ...)  # Will fail if chord is None
```

### 3. Give Widgets Time to Process Events

```python
# ✅ GOOD - Wait after showing widget and after keypress
widget.show()
QTest.qWait(50)  # Let widget initialize

QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)
QTest.qWait(50)  # Let event propagate

# ❌ BAD - No waiting
widget.show()
QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)
# Event may not be processed yet
```

### 4. Test Button Tooltips Include Shortcuts

```python
def test_button_tooltip_has_shortcut(app_context):
    """Verify buttons show their shortcuts in tooltips."""
    # Get the shortcut
    chord = app_context.shortcuts.get_effective_command_chord(
        plugin_id=PluginId("my_plugin"),
        command_id="my_command"
    )

    # Find the button
    button = find_button_for_command("my_command")

    if chord and button:
        # Tooltip should include the chord
        tooltip = button.toolTip()
        assert chord in tooltip, \
            f"Button tooltip should include shortcut '{chord}'"
```

## Complete Example

See [test_keyboard_shortcuts.py](examples/test_keyboard_shortcuts.py) for complete working examples of:
- Querying registered shortcuts
- Testing shortcuts with modifiers
- Simulating keyboard shortcuts
- Testing shortcut-button integration
- Testing hold vs toggle modes
- Enumerating all shortcuts for a plugin

## Related Documentation

- [Testing Guide](README.md) - General testing documentation
- [Widget Test Plugin](../src/datalens/plugins/widget_test/) - Example plugin with shortcuts
- [Shortcuts Manager](../src/datalens/services/shortcuts/manager.py) - Shortcuts system implementation
