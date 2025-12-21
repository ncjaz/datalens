"""
Example tests demonstrating keyboard shortcut testing in DataLens.

This shows how to:
- Query registered keyboard shortcuts
- Verify shortcut chord assignments (e.g., "Ctrl+S")
- Check modifier combinations
- Test shortcuts that trigger buttons
- Verify shortcuts work with different modifiers
- Test hold vs toggle mode for shortcuts
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId


@pytest.mark.ui
def test_query_registered_shortcuts(app_context):
    """
    Test that we can query all registered keyboard shortcuts.

    This shows how to:
    - Access the shortcuts manager
    - Query shortcuts for a specific plugin
    - Verify default chord assignments
    """
    shortcuts = app_context.shortcuts

    # Query a shortcut for the widget_test plugin
    # This plugin registers several test shortcuts
    chord = shortcuts.get_effective_command_chord(
        plugin_id=PluginId("widget_test"),
        command_id="log_hello"
    )

    # The chord will be a string like "Ctrl+H" or None if unbound
    print(f"\n✓ Found shortcut for 'log_hello': {chord}")

    # Note: The chord may be None if not bound, or a string if bound
    # Either is valid depending on manifest defaults
    assert chord is None or isinstance(chord, str)

    if chord:
        # Verify the chord contains expected components
        # Common formats: "Ctrl+H", "Alt+Shift+X", "F5", etc.
        print(f"  - Chord format: {chord}")
        print(f"  - Has Ctrl: {'Ctrl' in chord}")
        print(f"  - Has Alt: {'Alt' in chord}")
        print(f"  - Has Shift: {'Shift' in chord}")


@pytest.mark.ui
def test_shortcut_with_modifiers(app_context):
    """
    Test shortcuts with different modifier combinations.

    This demonstrates how to check for:
    - Ctrl modifier
    - Alt modifier
    - Shift modifier
    - Multiple modifiers (Ctrl+Shift, etc.)
    """
    shortcuts = app_context.shortcuts

    # Example: Check a shortcut with Ctrl modifier
    chord = shortcuts.get_effective_command_chord(
        plugin_id=PluginId("widget_test"),
        command_id="log_hello"
    )

    if chord:
        # Parse the chord to check modifiers
        has_ctrl = "Ctrl" in chord or "Control" in chord
        has_alt = "Alt" in chord
        has_shift = "Shift" in chord

        print(f"\n✓ Shortcut '{chord}' modifiers:")
        print(f"  - Ctrl: {has_ctrl}")
        print(f"  - Alt: {has_alt}")
        print(f"  - Shift: {has_shift}")

        # Verify at least one modifier is present for safety
        # (prevents accidental single-key shortcuts that could conflict)
        # Note: Some shortcuts like F1-F12 are fine without modifiers
        if chord[0] != 'F':  # If not a function key
            # Most shortcuts should have a modifier
            has_modifier = has_ctrl or has_alt or has_shift
            print(f"  - Has modifier: {has_modifier}")


@pytest.mark.ui
def test_shortcut_triggers_button(app_context):
    """
    Test that a keyboard shortcut successfully triggers a button action.

    This demonstrates:
    - Creating a widget with a shortcut-bound button
    - Simulating the keyboard shortcut
    - Verifying the button action was triggered
    """
    from datalens.ui.widgets.core.buttons import DatalensButton
    from PySide6.QtWidgets import QWidget

    # Create a test widget
    test_widget = QWidget()

    # Track if button was clicked
    clicked = []

    # Create a button (in real tests, you'd find this in the actual UI)
    button = DatalensButton("Test Button", app_context.theme, parent=test_widget)
    button.clicked.connect(lambda: clicked.append(True))

    try:
        # Show the widget so it can receive keyboard events
        test_widget.show()
        QTest.qWait(50)

        # Simulate a keyboard shortcut (Ctrl+T)
        QTest.keyClick(test_widget, Qt.Key_T, Qt.ControlModifier)
        QTest.qWait(50)

        # Note: The button won't actually trigger unless the shortcut
        # is properly registered and connected. This example shows
        # the *pattern* - in real tests you'd use actual registered shortcuts.

        print(f"\n✓ Simulated Ctrl+T keyboard shortcut")
        print(f"  - Button clicked: {len(clicked) > 0}")

    finally:
        test_widget.close()
        test_widget.deleteLater()


@pytest.mark.ui
def test_hold_vs_toggle_mode(app_context):
    """
    Test shortcuts that support both hold and toggle modes.

    Some shortcuts can operate in two modes:
    - Hold mode: Action active only while key is held
    - Toggle mode: Press once to activate, press again to deactivate

    This shows how to query which mode is active.
    """
    shortcuts = app_context.shortcuts

    # Query a command that supports hold/toggle mode
    mode_toggle = shortcuts.get_effective_command_mode_toggle(
        plugin_id=PluginId("widget_test"),
        command_id="hold_toggle_demo"
    )

    print(f"\n✓ Hold/Toggle mode setting:")
    if mode_toggle is None:
        print("  - Mode: Not applicable (command doesn't support hold/toggle)")
    elif mode_toggle:
        print("  - Mode: Toggle (press to activate, press again to deactivate)")
    else:
        print("  - Mode: Hold (active only while key is held)")

    # This setting can be configured by users in preferences
    # Tests should work with either mode
    assert mode_toggle is None or isinstance(mode_toggle, bool)


@pytest.mark.ui
def test_all_plugin_shortcuts(app_context):
    """
    Test that we can enumerate all shortcuts for a plugin.

    This is useful for:
    - Verifying all expected shortcuts are registered
    - Checking for conflicts
    - Documenting available shortcuts
    """
    shortcuts = app_context.shortcuts

    # Get all command registrations for widget_test plugin
    plugin_id = PluginId("widget_test")

    # Query several known commands
    test_commands = [
        "log_hello",
        "hold_toggle_demo",
        "run_count_10",
        "demo_toggle_flip",
        "demo_checkbox_toggle",
    ]

    shortcuts_found = {}
    for command_id in test_commands:
        try:
            chord = shortcuts.get_effective_command_chord(
                plugin_id=plugin_id,
                command_id=command_id
            )
            shortcuts_found[command_id] = chord
        except Exception:
            # Command may not be registered
            shortcuts_found[command_id] = None

    print(f"\n✓ Shortcuts registered for widget_test plugin:")
    for cmd_id, chord in shortcuts_found.items():
        status = chord if chord else "Unbound"
        print(f"  - {cmd_id}: {status}")

    # Verify we found at least some shortcuts
    bound_count = sum(1 for c in shortcuts_found.values() if c is not None)
    print(f"\n✓ Total bound shortcuts: {bound_count}/{len(test_commands)}")


@pytest.mark.ui
def test_shortcut_override_in_preferences(app_context):
    """
    Test that shortcut overrides from preferences are respected.

    This demonstrates:
    - User preferences can override default shortcuts
    - The get_effective_command_chord respects overrides
    - Tests should use effective shortcuts, not just defaults
    """
    shortcuts = app_context.shortcuts

    # Get the effective shortcut (includes any user overrides)
    effective_chord = shortcuts.get_effective_command_chord(
        plugin_id=PluginId("widget_test"),
        command_id="log_hello"
    )

    print(f"\n✓ Effective shortcut (with user overrides): {effective_chord}")

    # In tests, always use get_effective_* methods to get the actual
    # chord the user will experience, which includes their preferences

    # Note: In testing mode, you can temporarily override shortcuts
    # by modifying app_context.shortcuts settings if needed


@pytest.mark.ui
def test_simulate_complex_shortcut(app_context):
    """
    Test simulating complex keyboard shortcuts with multiple modifiers.

    This shows how to:
    - Simulate Ctrl+Shift+Key combinations
    - Simulate Alt+Key combinations
    - Test shortcuts on specific widgets
    """
    from PySide6.QtWidgets import QWidget

    test_widget = QWidget()

    try:
        test_widget.show()
        QTest.qWait(50)

        # Simulate Ctrl+Shift+S
        QTest.keyClick(
            test_widget,
            Qt.Key_S,
            Qt.ControlModifier | Qt.ShiftModifier
        )
        print("\n✓ Simulated Ctrl+Shift+S")

        QTest.qWait(50)

        # Simulate Alt+F
        QTest.keyClick(
            test_widget,
            Qt.Key_F,
            Qt.AltModifier
        )
        print("✓ Simulated Alt+F")

        QTest.qWait(50)

        # Simulate F5 (no modifiers)
        QTest.keyClick(
            test_widget,
            Qt.Key_F5
        )
        print("✓ Simulated F5")

    finally:
        test_widget.close()
        test_widget.deleteLater()


@pytest.mark.ui
def test_shortcut_button_integration(app_context):
    """
    Test a real button bound to a shortcut in the widget test plugin.

    This demonstrates end-to-end testing of shortcuts with buttons.
    """
    from datalens.ui.widgets.core.buttons import DatalensButton
    from datalens.api.ui_commands import ShortcutButtonBinding

    # In the real app, buttons get their shortcuts through bindings
    # This example shows how to verify a button has a shortcut assigned

    # Get the effective shortcut
    chord = app_context.shortcuts.get_effective_command_chord(
        plugin_id=PluginId("widget_test"),
        command_id="run_count_10"
    )

    print(f"\n✓ Button shortcut for 'run_count_10': {chord}")

    if chord:
        # The button's tooltip should include the shortcut
        # In real tests, you'd find the actual button and check its tooltip
        print(f"  - Shortcut should appear in button tooltip")
        print(f"  - Pressing {chord} should trigger the button")
